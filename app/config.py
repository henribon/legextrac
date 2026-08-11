"""Configuracao lida de variaveis de ambiente / .env."""

import os

from dotenv import load_dotenv

load_dotenv()


def _clean(name: str, default: str = "") -> str:
    """Le a variavel tratando os placeholders do .env.example como vazio."""
    value = os.getenv(name, default).strip()
    return "" if value.startswith("sua-chave") else value


# Provedor de traducao: "gemini" ou "deepl".
TRANSLATOR = os.getenv("TRANSLATOR", "gemini").strip().lower()

# --- Gemini ---------------------------------------------------------------
GEMINI_API_KEY = _clean("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
# Requisicoes por minuto. O plano gratuito fica na casa de 10-15 RPM; passar
# disso rende 429. Ajuste conforme o limite que aparece no seu AI Studio.
GEMINI_RPM = int(os.getenv("GEMINI_RPM", "10"))
# Lotes grandes dao mais contexto ao modelo, mas aumentam a chance de ele
# perder o alinhamento e forcar reenvio dividido.
GEMINI_MAX_ITEMS_PER_REQUEST = int(os.getenv("GEMINI_MAX_ITEMS_PER_REQUEST", "60"))
GEMINI_MAX_CHARS_PER_REQUEST = int(os.getenv("GEMINI_MAX_CHARS_PER_REQUEST", "6000"))

# --- DeepL ----------------------------------------------------------------
DEEPL_API_KEY = _clean("DEEPL_API_KEY")

# Chaves gratuitas do DeepL terminam com ":fx" e usam um host diferente.
_DEFAULT_DEEPL_URL = (
    "https://api-free.deepl.com/v2/translate"
    if DEEPL_API_KEY.endswith(":fx")
    else "https://api.deepl.com/v2/translate"
)
DEEPL_API_URL = os.getenv("DEEPL_API_URL", _DEFAULT_DEEPL_URL).strip()

DEFAULT_TARGET_LANG = os.getenv("DEFAULT_TARGET_LANG", "PT-BR").strip()

YT_PROXY_HTTP = os.getenv("YT_PROXY_HTTP", "").strip() or None
YT_PROXY_HTTPS = os.getenv("YT_PROXY_HTTPS", "").strip() or None

# Limites do DeepL por requisicao: 50 textos e ~128 KiB de corpo.
DEEPL_MAX_TEXTS_PER_REQUEST = 50
DEEPL_MAX_CHARS_PER_REQUEST = 100_000
