"""Configuracao lida de variaveis de ambiente / .env."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _pasta_do_app() -> Path:
    """Onde o programa esta rodando.

    Empacotado com PyInstaller, __file__ aponta para a pasta temporaria em que
    o exe se descompacta -- inutil para achar configuracao. O que vale nesse
    caso e a pasta do proprio executavel.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


# Pasta de configuracao do usuario: e onde o .exe autonomo procura a chave,
# ja que ele pode estar em qualquer lugar do disco.
PASTA_CONFIG = Path(os.getenv("APPDATA", Path.home())) / "legextrac"

# Primeiro achado vence; variaveis ja definidas no sistema tem prioridade sobre
# todos eles (load_dotenv nao sobrescreve o que existe).
for _candidato in (Path.cwd() / ".env", _pasta_do_app() / ".env", PASTA_CONFIG / ".env"):
    if _candidato.is_file():
        load_dotenv(_candidato)
        ARQUIVO_ENV: Path | None = _candidato
        break
else:
    ARQUIVO_ENV = None


def _clean(name: str, default: str = "") -> str:
    """Le a variavel tratando os placeholders do .env.example como vazio."""
    value = os.getenv(name, default).strip()
    return "" if value.startswith("sua-chave") else value


def _flag(name: str, default: bool) -> bool:
    valor = os.getenv(name, "").strip().lower()
    if not valor:
        return default
    return valor not in ("0", "false", "nao", "no", "off")


# Provedor de traducao: "gemini" ou "deepl".
TRANSLATOR = os.getenv("TRANSLATOR", "gemini").strip().lower()

# --- Gemini ---------------------------------------------------------------
GEMINI_API_KEY = _clean("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
# "low" basta para traduzir. Vazio omite o campo (util se o modelo recusar).
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "low").strip()
# Requisicoes por minuto. O plano gratuito fica na casa de 10-15 RPM; passar
# disso rende 429. Ajuste conforme o limite que aparece no seu AI Studio.
GEMINI_RPM = int(os.getenv("GEMINI_RPM", "10"))
# Lotes grandes dao mais contexto ao modelo, mas aumentam a chance de ele
# perder o alinhamento e forcar reenvio dividido.
GEMINI_MAX_ITEMS_PER_REQUEST = int(os.getenv("GEMINI_MAX_ITEMS_PER_REQUEST", "60"))
GEMINI_MAX_CHARS_PER_REQUEST = int(os.getenv("GEMINI_MAX_CHARS_PER_REQUEST", "6000"))

# Modelo usado para DITAR o audio (Instagram, TikTok, YouTube sem legenda).
# Vazio = o mesmo GEMINI_MODEL da traducao.
GEMINI_TRANSCRIBE_MODEL = os.getenv("GEMINI_TRANSCRIBE_MODEL", "").strip()
# Teto da resposta. Transcricao de video longo e um texto grande: apertado
# demais, o modelo corta a legenda no meio.
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "65536"))

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

# Pasta onde os .txt sao gravados. Relativo = a partir da raiz do projeto.
# Vazio (padrao) = pasta Downloads do usuario.
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "").strip()

YT_PROXY_HTTP = os.getenv("YT_PROXY_HTTP", "").strip() or None
YT_PROXY_HTTPS = os.getenv("YT_PROXY_HTTPS", "").strip() or None

# Limites do DeepL por requisicao: 50 textos e ~128 KiB de corpo.
DEEPL_MAX_TEXTS_PER_REQUEST = 50
DEEPL_MAX_CHARS_PER_REQUEST = 100_000

# --- Midia (Instagram, TikTok, X, Facebook...) -----------------------------
# Sites que nao publicam legenda passam por download + transcricao do audio.

# Quando o video do YouTube nao tem legenda (ou o IP esta limitado), tenta
# pelo audio em vez de falhar. Custa cota do Gemini, por isso da para desligar.
AUDIO_FALLBACK = _flag("AUDIO_FALLBACK", True)

# Teto de duracao para transcricao por audio. Video longo vira texto longo, e
# texto longo custa cota -- suba so ate onde o seu plano do Gemini aguentar.
MEDIA_MAX_MINUTES = int(os.getenv("MEDIA_MAX_MINUTES", "30"))

# Instagram e TikTok escondem boa parte do conteudo atras de login.
# Reaproveita a sessao ja aberta no navegador: chrome, edge, firefox, brave...
# Aceita "chrome:Profile 2" para escolher o perfil.
COOKIES_FROM_BROWSER = os.getenv("COOKIES_FROM_BROWSER", "").strip()
# Alternativa: arquivo cookies.txt no formato Netscape. Tem prioridade.
COOKIES_FILE = os.getenv("COOKIES_FILE", "").strip()
