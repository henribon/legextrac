"""Traducao via API do Gemini.

Diferente de um tradutor classico, o modelo ve varias falas de uma vez e traduz
com o contexto do trecho inteiro, o que mantem termos e tom consistentes ao longo
do video. Em troca, ele pode juntar, dividir ou pular itens -- por isso a resposta
vem em JSON com ids e e conferida item a item.
"""

import json
import threading
import time
from collections.abc import Iterator

import httpx

from .. import config
from .base import TranslationError

_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# Nomes por extenso rendem traducao melhor do que codigos como "PT-BR".
_LANG_NAMES = {
    "PT-BR": "portugues do Brasil",
    "PT-PT": "portugues de Portugal",
    "PT": "portugues do Brasil",
    "EN-US": "ingles americano",
    "EN-GB": "ingles britanico",
    "EN": "ingles",
    "ES": "espanhol",
    "FR": "frances",
    "DE": "alemao",
    "IT": "italiano",
    "JA": "japones",
}

_PROMPT = """Voce traduz legendas de video para {target}.

Voce recebe um JSON com falas numeradas, na ordem em que aparecem no video.
Traduza cada fala seguindo estas regras:

- Devolva exatamente um item para cada item recebido, com o mesmo "id".
- Nunca junte nem divida itens, mesmo que uma frase pareca cortada no meio.
- Use o contexto das falas vizinhas para escolher o sentido certo das palavras.
- Tom natural de fala, como uma legenda de verdade -- nao traduza ao pe da letra.
- Mantenha nomes proprios, siglas, numeros e termos tecnicos consagrados.
- Nao adicione comentarios, notas, reticencias ou aspas que nao existam no original.
- Se um item nao precisar de traducao, devolva o texto original.

Falas:
{payload}"""

_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "INTEGER"},
            "text": {"type": "STRING"},
        },
        "required": ["id", "text"],
    },
}

_rate_lock = threading.Lock()
_last_call = 0.0


def _throttle() -> None:
    """Espaca as chamadas para respeitar o limite de requisicoes por minuto.

    O plano gratuito do Gemini limita por requisicao, nao por caractere, entao
    estourar o RPM e o unico jeito realista de tomar 429 aqui.
    """
    global _last_call
    if config.GEMINI_RPM <= 0:
        return
    interval = 60.0 / config.GEMINI_RPM
    with _rate_lock:
        wait = _last_call + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def _batches(texts: list[str]) -> Iterator[tuple[int, list[str]]]:
    """Divide em lotes por quantidade e por tamanho, preservando a ordem."""
    batch: list[str] = []
    start = 0
    size = 0
    for index, text in enumerate(texts):
        if batch and (
            len(batch) >= config.GEMINI_MAX_ITEMS_PER_REQUEST
            or size + len(text) > config.GEMINI_MAX_CHARS_PER_REQUEST
        ):
            yield start, batch
            batch, start, size = [], index, 0
        batch.append(text)
        size += len(text)
    if batch:
        yield start, batch


def _target_name(target_lang: str) -> str:
    return _LANG_NAMES.get(target_lang.upper(), target_lang)


def _body(prompt: str, thinking: bool) -> dict:
    config_gen: dict = {
        "temperature": 0.0,
        "responseMimeType": "application/json",
        "responseSchema": _SCHEMA,
        "maxOutputTokens": 16384,
    }
    if thinking and config.GEMINI_THINKING_LEVEL:
        # Traduzir nao precisa de raciocinio longo; o nivel baixo corta
        # latencia e consumo de tokens. O campo mudou de nome entre geracoes
        # de modelo (thinkingBudget no 2.x, thinkingLevel no 3.x), por isso a
        # chamada sabe se recuperar quando ele e recusado.
        config_gen["thinkingConfig"] = {"thinkingLevel": config.GEMINI_THINKING_LEVEL}
    return {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config_gen}


def _call(client: httpx.Client, prompt: str) -> str:
    url = _ENDPOINT.format(model=config.GEMINI_MODEL)
    headers = {"x-goog-api-key": config.GEMINI_API_KEY}
    thinking = True
    body = _body(prompt, thinking)

    last_error = ""
    for attempt in range(3):
        _throttle()
        try:
            response = client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise TranslationError(f"Falha de rede ao chamar o Gemini: {exc}") from exc

        if response.status_code == 200:
            data = response.json()
            candidates = data.get("candidates") or []
            if not candidates:
                # Sem candidato costuma ser bloqueio do filtro de seguranca.
                reason = data.get("promptFeedback", {}).get("blockReason", "desconhecido")
                raise TranslationError(f"Gemini nao retornou traducao (motivo: {reason}).")
            parts = candidates[0].get("content", {}).get("parts") or []
            text = "".join(part.get("text", "") for part in parts)
            if not text.strip():
                finish = candidates[0].get("finishReason", "desconhecido")
                raise TranslationError(f"Gemini retornou resposta vazia ({finish}).")
            return text

        if response.status_code in (429, 500, 503):
            # 429 = cota/RPM, 503 = modelo sobrecarregado. Ambos passam com espera.
            last_error = f"{response.status_code}: {response.text[:200]}"
            time.sleep(2 ** attempt * 5)
            continue

        if response.status_code in (400, 403) and "API_KEY" in response.text.upper():
            raise TranslationError("Gemini recusou a chave de API (GEMINI_API_KEY invalida).")

        if response.status_code == 400 and thinking:
            # Geracoes diferentes de modelo aceitam campos de "thinking"
            # diferentes. Se foi isso, uma tentativa sem o campo resolve.
            thinking = False
            body = _body(prompt, thinking)
            continue

        if response.status_code == 404:
            raise TranslationError(
                f"O modelo '{config.GEMINI_MODEL}' nao esta disponivel para esta chave. "
                "Rode 'python -m app.models_disponiveis' para ver a lista e ajuste "
                "GEMINI_MODEL no .env."
            )

        raise TranslationError(
            f"Gemini respondeu {response.status_code}: {response.text[:300]}"
        )

    raise TranslationError(f"Gemini indisponivel apos 3 tentativas ({last_error}).")


def _translate_batch(client: httpx.Client, texts: list[str], target: str) -> list[str]:
    """Traduz um lote e confere o alinhamento; em caso de falha, divide ao meio."""
    payload = json.dumps(
        [{"id": i, "text": t} for i, t in enumerate(texts)], ensure_ascii=False
    )
    raw = _call(client, _PROMPT.format(target=target, payload=payload))

    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        items = None

    if isinstance(items, list):
        by_id: dict[int, str] = {}
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("id"), int):
                by_id[item["id"]] = str(item.get("text", ""))
        if len(by_id) == len(texts) and all(i in by_id for i in range(len(texts))):
            return [by_id[i] for i in range(len(texts))]

    # O modelo perdeu o alinhamento. Lotes menores tem muito menos chance de
    # errar; um item sozinho e praticamente impossivel de desalinhar.
    if len(texts) > 1:
        meio = len(texts) // 2
        return _translate_batch(client, texts[:meio], target) + _translate_batch(
            client, texts[meio:], target
        )

    raise TranslationError(
        "Gemini devolveu a traducao fora do formato esperado, mesmo item a item."
    )


def translate(
    texts: list[str],
    target_lang: str | None = None,
    source_lang: str | None = None,
) -> list[str]:
    """Traduz uma lista de textos preservando a ordem (1 entrada -> 1 saida)."""
    if not config.GEMINI_API_KEY:
        raise TranslationError(
            "GEMINI_API_KEY nao configurada. Pegue uma chave em "
            "https://aistudio.google.com/apikey e coloque no .env."
        )
    if not texts:
        return []

    target = _target_name(target_lang or config.DEFAULT_TARGET_LANG)
    result: list[str] = []
    with httpx.Client(timeout=180.0) as client:
        for _, batch in _batches(texts):
            result.extend(_translate_batch(client, batch, target))
    return result
