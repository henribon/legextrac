"""Extracao da legenda publicada de videos do YouTube.

Este e o caminho preferido quando o link e do YouTube: a legenda ja existe
pronta no servidor, entao sai de graca, na hora e com os tempos exatos. Sites
que nao publicam legenda (Instagram, TikTok...) passam pelo caminho do audio,
em `speech.py`.
"""

import re
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi

try:  # exportados no pacote raiz nas versoes recentes
    from youtube_transcript_api import (
        AgeRestricted,
        CouldNotRetrieveTranscript,
        NoTranscriptFound,
        RequestBlocked,
        TranscriptsDisabled,
        VideoUnavailable,
    )
except ImportError:  # pragma: no cover
    from youtube_transcript_api._errors import (
        AgeRestricted,
        CouldNotRetrieveTranscript,
        NoTranscriptFound,
        RequestBlocked,
        TranscriptsDisabled,
        VideoUnavailable,
    )

from . import config
from .transcript import Snippet, Transcript, TranscriptError

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_PATH_PREFIXES = ("/embed/", "/shorts/", "/v/", "/live/")


class SemLegenda(TranscriptError):
    """O video existe, mas nao da para pegar a legenda pronta dele.

    Separado do erro generico porque so este caso vale a pena tentar de novo
    ditando o audio: video sem legenda, legenda desativada ou IP limitado.
    """


def _host(url: str) -> str:
    if "://" not in url:
        url = "https://" + url
    return urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")


def is_youtube(url: str) -> bool:
    """Diz se o link vai pelo caminho da legenda pronta, sem levantar erro."""
    url = (url or "").strip()
    if not url:
        return False
    if _VIDEO_ID_RE.match(url):
        return True
    host = _host(url)
    return (
        host in ("youtu.be", "youtube.com")
        or host.endswith(".youtube.com")
        or host.endswith("youtube-nocookie.com")
    )


def extract_video_id(url: str) -> str:
    """Aceita links watch/youtu.be/shorts/embed/live ou o proprio ID de 11 caracteres."""
    url = (url or "").strip()
    if not url:
        raise TranscriptError("URL vazia.")
    if _VIDEO_ID_RE.match(url):
        return url

    if "://" not in url:
        url = "https://" + url

    parsed = urlparse(url)
    host = _host(url)

    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        candidate = ""
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        else:
            for prefix in _PATH_PREFIXES:
                if parsed.path.startswith(prefix):
                    candidate = parsed.path[len(prefix) :].split("/")[0]
                    break
    else:
        raise TranscriptError(f"Nao parece um link do YouTube: {url}")

    if not _VIDEO_ID_RE.match(candidate):
        raise TranscriptError(f"Nao foi possivel extrair o ID do video de: {url}")
    return candidate


def _proxy_config():
    if not (config.YT_PROXY_HTTP or config.YT_PROXY_HTTPS):
        return None
    try:
        from youtube_transcript_api.proxies import GenericProxyConfig
    except ImportError:  # versao antiga da lib, sem suporte a proxy
        return None
    return GenericProxyConfig(
        http_url=config.YT_PROXY_HTTP,
        https_url=config.YT_PROXY_HTTPS,
    )


def _list_transcripts(video_id: str):
    """Compatibilidade entre a API 1.x (instancia) e a 0.6.x (estatica)."""
    if hasattr(YouTubeTranscriptApi, "list_transcripts"):  # API 0.6.x
        proxies = {}
        if config.YT_PROXY_HTTP:
            proxies["http"] = config.YT_PROXY_HTTP
        if config.YT_PROXY_HTTPS:
            proxies["https"] = config.YT_PROXY_HTTPS
        return YouTubeTranscriptApi.list_transcripts(video_id, proxies=proxies or None)

    proxy = _proxy_config()  # API 1.x
    api = YouTubeTranscriptApi(proxy_config=proxy) if proxy else YouTubeTranscriptApi()
    return api.list(video_id)


def _pick(transcript_list):
    """Escolhe sempre a legenda no idioma original falado no video.

    Um video popular pode ter dezenas de legendas traduzidas pela comunidade;
    traduzir uma delas seria traduzir uma traducao. Para achar a original:

    1. O YouTube so gera legenda automatica (ASR) no idioma do audio, entao a
       existencia dela revela qual e o idioma falado.
    2. Nesse idioma, a legenda escrita por humano (quando existe) e melhor que a
       ASR: tem pontuacao e nao erra palavras. Mesmo conteudo, mais qualidade.
    3. Sem ASR (video com legenda so manual), usa-se a primeira faixa da lista:
       o YouTube devolve a faixa padrao do video em primeiro lugar.
    """
    available = list(transcript_list)
    if not available:
        raise SemLegenda("Este video nao possui legendas disponiveis.")

    manual = [t for t in available if not t.is_generated]
    generated = [t for t in available if t.is_generated]

    if generated:
        spoken = generated[0].language_code.split("-")[0].lower()
        for t in manual:
            if t.language_code.split("-")[0].lower() == spoken:
                return t
        return generated[0]

    return manual[0]


def _to_snippets(fetched) -> list[Snippet]:
    out: list[Snippet] = []
    for item in fetched:
        if isinstance(item, dict):  # API 0.6.x
            text, start, duration = item["text"], item["start"], item["duration"]
        else:  # API 1.x
            text, start, duration = item.text, item.start, item.duration
        text = " ".join(text.split())
        if text:
            out.append(Snippet(text=text, start=float(start), duration=float(duration)))
    return out


def fetch_title(video_id: str) -> str | None:
    """Busca o titulo do video pelo oEmbed publico do YouTube.

    Serve so para nomear o arquivo de saida, entao qualquer falha aqui e
    ignorada: sem titulo, o arquivo fica com o ID do video.
    """
    try:
        import httpx

        response = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=10.0,
        )
        if response.status_code == 200:
            title = response.json().get("title")
            return title.strip() if isinstance(title, str) and title.strip() else None
    except Exception:
        pass
    return None


def fetch_captions(url: str) -> Transcript:
    """Busca a legenda publicada do video, no idioma original em que foi falado."""
    video_id = extract_video_id(url)
    try:
        transcript_list = _list_transcripts(video_id)
        chosen = _pick(transcript_list)
        snippets = _to_snippets(chosen.fetch())
    except TranscriptsDisabled as exc:
        raise SemLegenda("As legendas estao desativadas neste video.") from exc
    except NoTranscriptFound as exc:
        raise SemLegenda("Nenhuma legenda encontrada para este video.") from exc
    except VideoUnavailable as exc:
        raise TranscriptError("Video indisponivel ou privado.") from exc
    except AgeRestricted as exc:
        raise TranscriptError("Video com restricao de idade: o YouTube exige login.") from exc
    except RequestBlocked as exc:
        # O YouTube limita por IP o endpoint que serve o TEXTO da legenda. O
        # resto do site continua respondendo normalmente, entao nao adianta
        # testar abrindo o video no navegador: parece tudo certo.
        raise SemLegenda(
            "O YouTube esta limitando as requisicoes de legenda deste IP (HTTP 429). "
            "Nao e a chave nem o video. Opcoes: esperar algumas horas, usar outra rede "
            "(dados moveis, por exemplo), ou configurar YT_PROXY_HTTP no .env. "
            "Rode python -m app.diagnostico URL para confirmar."
        ) from exc
    except CouldNotRetrieveTranscript as exc:
        raise SemLegenda(f"Nao foi possivel obter a legenda: {exc}") from exc

    if not snippets:
        raise SemLegenda("A legenda veio vazia.")

    return Transcript(
        video_id=video_id,
        language=getattr(chosen, "language", "desconhecido"),
        language_code=getattr(chosen, "language_code", ""),
        is_generated=bool(getattr(chosen, "is_generated", False)),
        snippets=snippets,
        title=fetch_title(video_id),
        source="youtube",
        source_url=f"https://www.youtube.com/watch?v={video_id}",
        method="legenda",
    )
