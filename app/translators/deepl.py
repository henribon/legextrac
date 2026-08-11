"""Traducao via API REST do DeepL."""

from collections.abc import Iterator

import httpx

from .. import config
from .base import TranslationError

# Idiomas que o DeepL aceita como ORIGEM. Como a legenda original pode vir em
# qualquer idioma, mandar um codigo fora desta lista faria o DeepL responder 400.
# Nesses casos e melhor omitir o campo e deixar o DeepL detectar sozinho.
DEEPL_SOURCE_LANGS = {
    "AR", "BG", "CS", "DA", "DE", "EL", "EN", "ES", "ET", "FI", "FR", "HE", "HU",
    "ID", "IT", "JA", "KO", "LT", "LV", "NB", "NL", "PL", "PT", "RO", "RU", "SK",
    "SL", "SV", "TH", "TR", "UK", "VI", "ZH",
}


def _batches(texts: list[str]) -> Iterator[list[str]]:
    """Respeita os limites do DeepL: 50 textos e ~128 KiB por requisicao."""
    batch: list[str] = []
    size = 0
    for text in texts:
        if batch and (
            len(batch) >= config.DEEPL_MAX_TEXTS_PER_REQUEST
            or size + len(text) > config.DEEPL_MAX_CHARS_PER_REQUEST
        ):
            yield batch
            batch, size = [], 0
        batch.append(text)
        size += len(text)
    if batch:
        yield batch


def translate(
    texts: list[str],
    target_lang: str | None = None,
    source_lang: str | None = None,
) -> list[str]:
    """Traduz uma lista de textos preservando a ordem (1 entrada -> 1 saida)."""
    if not config.DEEPL_API_KEY:
        raise TranslationError(
            "DEEPL_API_KEY nao configurada. Copie .env.example para .env e preencha a chave."
        )
    if not texts:
        return []

    target = (target_lang or config.DEFAULT_TARGET_LANG).upper()
    payload_base: dict = {"target_lang": target}
    if source_lang:
        # DeepL espera a origem sem variante regional (EN, nao EN-US).
        base = source_lang.split("-")[0].upper()
        if base in DEEPL_SOURCE_LANGS:
            payload_base["source_lang"] = base

    headers = {"Authorization": f"DeepL-Auth-Key {config.DEEPL_API_KEY}"}
    result: list[str] = []

    with httpx.Client(timeout=60.0) as client:
        for batch in _batches(texts):
            try:
                response = client.post(
                    config.DEEPL_API_URL,
                    headers=headers,
                    json={**payload_base, "text": batch},
                )
            except httpx.HTTPError as exc:
                raise TranslationError(f"Falha de rede ao chamar o DeepL: {exc}") from exc

            if response.status_code == 403:
                raise TranslationError("DeepL recusou a chave de API (403).")
            if response.status_code == 456:
                raise TranslationError("Cota de caracteres do DeepL esgotada (456).")
            if response.status_code == 429:
                raise TranslationError("DeepL respondeu 429: muitas requisicoes, tente de novo.")
            if response.status_code >= 400:
                raise TranslationError(
                    f"DeepL respondeu {response.status_code}: {response.text[:300]}"
                )

            translations = response.json().get("translations", [])
            if len(translations) != len(batch):
                raise TranslationError("Resposta do DeepL com quantidade inesperada de textos.")
            result.extend(item["text"] for item in translations)

    return result
