"""Selecao do provedor de traducao via variavel TRANSLATOR."""

from .. import config
from .base import TranslationError

_PROVIDERS = ("gemini", "deepl")


def _module():
    provider = config.TRANSLATOR
    if provider == "gemini":
        from . import gemini

        return gemini
    if provider == "deepl":
        from . import deepl

        return deepl
    raise TranslationError(
        f"TRANSLATOR='{provider}' desconhecido. Use um destes: {', '.join(_PROVIDERS)}."
    )


def is_configured() -> bool:
    if config.TRANSLATOR == "gemini":
        return bool(config.GEMINI_API_KEY)
    if config.TRANSLATOR == "deepl":
        return bool(config.DEEPL_API_KEY)
    return False


def translate(
    texts: list[str],
    target_lang: str | None = None,
    source_lang: str | None = None,
) -> list[str]:
    return _module().translate(texts, target_lang=target_lang, source_lang=source_lang)


__all__ = ["TranslationError", "translate", "is_configured"]
