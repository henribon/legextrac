"""Transcricao da fala de um arquivo de midia, pelo Gemini.

Usado quando o site nao publica legenda -- Instagram, TikTok, X e afins. O
mesmo modelo que ja traduz tambem escuta audio e video, entao nao entra chave
nova nem modelo local pesado: reaproveita a GEMINI_API_KEY que ja existe.

Arquivo pequeno vai embutido na propria requisicao (base64). Acima disso, sobe
antes pela Files API, porque o corpo de uma chamada ao Gemini nao passa de
20 MB -- e base64 ainda incha o arquivo em um terco.
"""

import base64
import json
import time
from collections.abc import Callable

import httpx

from . import config
from .media import Media
from .transcript import Snippet, Transcript, TranscriptError
from .translators.gemini import throttle

_GERAR = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_UPLOAD = "https://generativelanguage.googleapis.com/upload/v1beta/files"
_ARQUIVOS = "https://generativelanguage.googleapis.com/v1beta"

# Acima disso o base64 estouraria o limite de 20 MB do corpo da requisicao.
_LIMITE_INLINE = 8 * 1024 * 1024

_PROMPT = """Transcreva a fala deste arquivo, palavra por palavra.

Regras:
- Transcreva no idioma original falado. Nao traduza nada.
- Quebre em falas curtas, de uma frase cada, na ordem em que sao ditas.
- start e end sao segundos desde o inicio do arquivo, com decimal.
- Pontue normalmente e use maiuscula onde a lingua pedir.
- Nao invente: trecho sem fala simplesmente nao vira item.
- Nao descreva imagem, musica nem ruido; so o que for falado.
- language: o nome do idioma por extenso, em portugues (ingles, espanhol...).
- language_code: o codigo ISO 639-1 do idioma (en, es, pt...).

Se o arquivo nao tiver nenhuma fala, devolva a lista de segmentos vazia."""

_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "language": {"type": "STRING"},
        "language_code": {"type": "STRING"},
        "segments": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "start": {"type": "NUMBER"},
                    "end": {"type": "NUMBER"},
                    "text": {"type": "STRING"},
                },
                "required": ["start", "end", "text"],
            },
        },
    },
    "required": ["language", "language_code", "segments"],
}


def _headers() -> dict:
    return {"x-goog-api-key": config.GEMINI_API_KEY}


def _modelo() -> str:
    return config.GEMINI_TRANSCRIBE_MODEL or config.GEMINI_MODEL


def _erro_http(response: httpx.Response) -> TranscriptError:
    if response.status_code in (400, 403) and "API_KEY" in response.text.upper():
        return TranscriptError("Gemini recusou a chave de API (GEMINI_API_KEY invalida).")
    if response.status_code == 404:
        return TranscriptError(
            f"O modelo {_modelo()} nao esta disponivel para esta chave. "
            "Rode python -m app.models_disponiveis e ajuste GEMINI_MODEL no .env."
        )
    if response.status_code == 429:
        return TranscriptError(
            "Cota do Gemini esgotada (HTTP 429). Audio consome bem mais token que texto: "
            "espere a cota renovar, use um video mais curto, ou troque GEMINI_MODEL por "
            "um modelo lite."
        )
    return TranscriptError(f"Gemini respondeu {response.status_code}: {response.text[:300]}")


# -- envio do arquivo -------------------------------------------------------


def _subir_arquivo(client: httpx.Client, media: Media) -> dict:
    """Sobe pela Files API (protocolo resumable) e espera ficar pronto."""
    tamanho = media.path.stat().st_size
    inicio = client.post(
        _UPLOAD,
        headers={
            **_headers(),
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(tamanho),
            "X-Goog-Upload-Header-Content-Type": media.mime,
            "Content-Type": "application/json",
        },
        json={"file": {"display_name": media.path.name}},
    )
    if inicio.status_code != 200:
        raise _erro_http(inicio)

    destino = inicio.headers.get("x-goog-upload-url")
    if not destino:
        raise TranscriptError("O Gemini nao devolveu o endereco de upload do arquivo.")

    envio = client.post(
        destino,
        headers={
            "Content-Length": str(tamanho),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
        content=media.path.read_bytes(),
    )
    if envio.status_code != 200:
        raise _erro_http(envio)

    arquivo = envio.json().get("file") or {}
    nome = arquivo.get("name")
    if not nome:
        raise TranscriptError("O Gemini aceitou o upload mas nao devolveu o identificador.")

    # Midia recem-enviada fica em PROCESSING por alguns segundos; usar antes
    # da hora responde 400.
    limite = time.monotonic() + 300
    while arquivo.get("state") == "PROCESSING":
        if time.monotonic() > limite:
            raise TranscriptError("O Gemini demorou demais para processar o arquivo enviado.")
        time.sleep(2)
        consulta = client.get(f"{_ARQUIVOS}/{nome}", headers=_headers())
        if consulta.status_code != 200:
            raise _erro_http(consulta)
        arquivo = consulta.json()

    if arquivo.get("state") != "ACTIVE":
        raise TranscriptError(f"O Gemini nao conseguiu ler o arquivo enviado ({arquivo.get('state')}).")
    return arquivo


def _apagar_arquivo(client: httpx.Client, nome: str) -> None:
    """Some sozinho em 48h, mas nao ha motivo para deixar a midia la."""
    try:
        client.delete(f"{_ARQUIVOS}/{nome}", headers=_headers())
    except httpx.HTTPError:
        pass


# -- chamada ao modelo ------------------------------------------------------


def _body(parte_midia: dict, nivel: int) -> dict:
    """`nivel` cresce a cada 400: vai tirando campo opcional ate o modelo aceitar."""
    gen: dict = {
        "temperature": 0.0,
        "responseMimeType": "application/json",
        "responseSchema": _SCHEMA,
    }
    if nivel < 2:
        gen["maxOutputTokens"] = config.GEMINI_MAX_OUTPUT_TOKENS
    if nivel < 1:
        if config.GEMINI_THINKING_LEVEL:
            gen["thinkingConfig"] = {"thinkingLevel": config.GEMINI_THINKING_LEVEL}
        midia = parte_midia.get("file_data") or parte_midia.get("inline_data") or {}
        if str(midia.get("mime_type", "")).startswith("video/"):
            # Transcricao nao olha a imagem; a resolucao baixa corta muito token.
            gen["mediaResolution"] = "MEDIA_RESOLUTION_LOW"

    return {
        "contents": [{"parts": [parte_midia, {"text": _PROMPT}]}],
        "generationConfig": gen,
    }


def _gerar(client: httpx.Client, parte_midia: dict) -> str:
    url = _GERAR.format(model=_modelo())
    nivel = 0
    ultimo = ""

    for tentativa in range(4):
        throttle()
        try:
            response = client.post(url, headers=_headers(), json=_body(parte_midia, nivel))
        except httpx.HTTPError as exc:
            raise TranscriptError(f"Falha de rede ao chamar o Gemini: {exc}") from exc

        if response.status_code == 200:
            dados = response.json()
            candidatos = dados.get("candidates") or []
            if not candidatos:
                motivo = dados.get("promptFeedback", {}).get("blockReason", "desconhecido")
                raise TranscriptError(
                    f"O Gemini recusou transcrever este audio (motivo: {motivo})."
                )
            fim = candidatos[0].get("finishReason", "")
            partes = candidatos[0].get("content", {}).get("parts") or []
            texto = "".join(p.get("text", "") for p in partes)
            if fim == "MAX_TOKENS":
                raise TranscriptError(
                    "A transcricao passou do limite de resposta do modelo. Use um video mais "
                    "curto ou aumente GEMINI_MAX_OUTPUT_TOKENS no .env."
                )
            if not texto.strip():
                raise TranscriptError(f"O Gemini devolveu resposta vazia ({fim or 'sem motivo'}).")
            return texto

        if response.status_code == 400 and nivel < 2:
            # Cada geracao de modelo aceita um conjunto diferente de campos
            # opcionais; se foi isso, tentar sem eles resolve.
            nivel += 1
            continue

        if response.status_code in (429, 500, 503):
            ultimo = f"{response.status_code}: {response.text[:200]}"
            time.sleep(2**tentativa * 5)
            continue

        raise _erro_http(response)

    raise TranscriptError(f"Gemini indisponivel apos varias tentativas ({ultimo}).")


# -- resultado --------------------------------------------------------------


def _snippets(segmentos: list, duracao: float | None) -> list[Snippet]:
    saida: list[Snippet] = []
    for item in segmentos:
        if not isinstance(item, dict):
            continue
        texto = " ".join(str(item.get("text", "")).split())
        if not texto:
            continue
        try:
            comeco = max(float(item.get("start", 0.0)), 0.0)
            fim = float(item.get("end", comeco))
        except (TypeError, ValueError):
            continue
        if duracao:
            comeco = min(comeco, duracao)
            fim = min(fim, duracao)
        saida.append(Snippet(text=texto, start=comeco, duration=max(fim - comeco, 0.0)))

    saida.sort(key=lambda s: s.start)
    return saida


def transcrever(media: Media, progresso: Callable[[str], None] | None = None) -> Transcript:
    """Manda a midia para o Gemini e devolve a fala transcrita com tempos."""
    if not config.GEMINI_API_KEY:
        raise TranscriptError(
            "Este link nao tem legenda publicada, entao o texto precisa ser ditado do audio "
            "pelo Gemini -- e a GEMINI_API_KEY nao esta configurada. Pegue uma chave gratuita "
            "em https://aistudio.google.com/apikey e coloque no .env."
        )

    def aviso(mensagem: str) -> None:
        if progresso:
            progresso(mensagem)

    tamanho = media.path.stat().st_size
    enviado: str | None = None

    with httpx.Client(timeout=900.0, follow_redirects=True) as client:
        try:
            if tamanho <= _LIMITE_INLINE:
                parte = {
                    "inline_data": {
                        "mime_type": media.mime,
                        "data": base64.b64encode(media.path.read_bytes()).decode("ascii"),
                    }
                }
            else:
                aviso(f"Enviando {tamanho / 1024 / 1024:.1f} MB ao Gemini...")
                arquivo = _subir_arquivo(client, media)
                enviado = arquivo["name"]
                parte = {"file_data": {"mime_type": media.mime, "file_uri": arquivo["uri"]}}

            aviso("Transcrevendo o audio (a parte demorada)...")
            bruto = _gerar(client, parte)
        finally:
            if enviado:
                _apagar_arquivo(client, enviado)

    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError as exc:
        raise TranscriptError("O Gemini devolveu a transcricao fora do formato esperado.") from exc

    if not isinstance(dados, dict):
        raise TranscriptError("O Gemini devolveu a transcricao fora do formato esperado.")

    snippets = _snippets(dados.get("segments") or [], media.duration)
    if not snippets:
        raise TranscriptError(
            "Nenhuma fala foi encontrada neste video (pode ser so musica ou imagem)."
        )

    codigo = str(dados.get("language_code") or "").strip().lower()
    return Transcript(
        video_id=media.media_id,
        language=str(dados.get("language") or "desconhecido").strip(),
        language_code=codigo,
        is_generated=True,
        snippets=snippets,
        title=media.title,
        source=media.source,
        source_url=media.source_url,
        method="audio",
    )
