"""Download do arquivo de midia de qualquer site suportado pelo yt-dlp.

Instagram, TikTok, X, Facebook, Vimeo, Reddit e outras centenas de sites nao
publicam faixa de legenda em lugar nenhum -- so existe o video. Para esses, o
unico caminho e baixar a midia e ditar o audio, que e o que `speech.py` faz
depois. Aqui so cuidamos de trazer o arquivo para o disco.

Com ffmpeg instalado, baixamos so a trilha de audio e convertemos para MP3:
arquivo pequeno e cobranca de tokens ~8x menor no Gemini. Sem ffmpeg, baixamos
o MP4 progressivo (video junto), que funciona igual porem sai mais caro -- por
isso o limite de duracao e menor nesse modo.
"""

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import config
from .transcript import TranscriptError

# Tipos que o Gemini aceita. O que nao estiver aqui nao adianta enviar.
_MIME = {
    ".mp3": "audio/mp3",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".m4a": "audio/aac",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/mov",
    ".3gp": "video/3gpp",
}

# Sem ffmpeg vai video junto com o audio, e video custa ~8x mais token por
# segundo. Acima disso a chance de estourar a cota por minuto e grande.
_MAX_MINUTOS_SEM_FFMPEG = 12


class MediaError(TranscriptError):
    """Falha esperada ao baixar a midia (mensagem exibivel ao usuario).

    Herda de TranscriptError para o resto do programa tratar "nao consegui a
    legenda" e "nao consegui a midia" do mesmo jeito: os dois viram a mesma
    mensagem na tela.
    """


@dataclass
class Media:
    path: Path
    mime: str
    source: str
    source_url: str
    media_id: str
    title: str | None
    duration: float | None


def tem_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _yt_dlp():
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover
        raise MediaError(
            "Falta a biblioteca yt-dlp, necessaria para links que nao sao do YouTube. "
            "Instale com: pip install -U yt-dlp"
        ) from exc
    return yt_dlp


class _Mudo:
    """Silencia o log do yt-dlp: quem fala com o usuario e a interface."""

    def debug(self, msg):
        pass

    info = warning = debug

    def error(self, msg):
        pass


def _cookies(opts: dict) -> None:
    """Instagram e TikTok escondem boa parte do conteudo atras de login."""
    if config.COOKIES_FILE:
        opts["cookiefile"] = config.COOKIES_FILE
        return
    if config.COOKIES_FROM_BROWSER:
        navegador, _, perfil = config.COOKIES_FROM_BROWSER.partition(":")
        opts["cookiesfrombrowser"] = (navegador.strip().lower(), perfil.strip() or None, None, None)


def _opcoes(destino: Path, com_ffmpeg: bool) -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "logger": _Mudo(),
        "socket_timeout": 30,
        "retries": 3,
        "outtmpl": str(destino / "%(id).80s.%(ext)s"),
        "paths": {"home": str(destino)},
    }
    if com_ffmpeg:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "64",
            }
        ]
    else:
        # Sem ffmpeg nao da para juntar faixas separadas de video e audio, entao
        # so serve formato ja combinado num arquivo so.
        opts["format"] = "best[ext=mp4]/best"
    _cookies(opts)
    return opts


def _traduzir_erro(url: str, mensagem: str) -> MediaError:
    baixo = mensagem.lower()

    if "unsupported url" in baixo or "no suitable extractor" in baixo:
        return MediaError(
            f"Nenhum extrator conhece este site: {url}\n"
            "Se o link estiver certo, um yt-dlp mais novo pode ja suportar: "
            "pip install -U yt-dlp"
        )
    if any(
        p in baixo
        for p in ("login required", "log in", "sign in", "cookies", "private", "registered users")
    ):
        return MediaError(
            "Este conteudo exige estar logado. Configure COOKIES_FROM_BROWSER no .env "
            "(ex.: COOKIES_FROM_BROWSER=chrome) para o programa reaproveitar a sessao do "
            "seu navegador, ou exporte um cookies.txt e aponte COOKIES_FILE para ele."
        )
    if "rate" in baixo and "limit" in baixo:
        return MediaError("O site esta limitando as requisicoes deste IP. Tente mais tarde.")
    if "video unavailable" in baixo or "not available" in baixo or "410" in baixo:
        return MediaError("Publicacao indisponivel, apagada ou restrita a certa regiao.")
    if "ffmpeg" in baixo:
        return MediaError(f"Falha no ffmpeg ao preparar o audio: {mensagem}")

    return MediaError(f"Nao foi possivel baixar a midia: {mensagem}")


def _extrair_info(ydl, url: str) -> dict:
    info = ydl.extract_info(url, download=False)
    # Perfil, playlist ou album: pega o primeiro item em vez de recusar tudo.
    while info and info.get("_type") in ("playlist", "multi_video"):
        entradas = [e for e in (info.get("entries") or []) if e]
        if not entradas:
            raise MediaError("O link aponta para uma colecao vazia, sem nenhum video.")
        info = entradas[0]
    if not info:
        raise MediaError("O site nao devolveu nenhuma midia para este link.")
    return info


def _conferir_duracao(duracao: float | None, com_ffmpeg: bool) -> None:
    if not duracao:
        return  # transmissao ao vivo ou site que nao informa; segue e torce
    minutos = duracao / 60.0
    if minutos > config.MEDIA_MAX_MINUTES:
        raise MediaError(
            f"Video de {minutos:.0f} min, acima do limite de {config.MEDIA_MAX_MINUTES} min "
            "para transcricao por audio. Aumente MEDIA_MAX_MINUTES no .env se a sua cota do "
            "Gemini aguentar."
        )
    if not com_ffmpeg and minutos > _MAX_MINUTOS_SEM_FFMPEG:
        raise MediaError(
            f"Video de {minutos:.0f} min. Sem o ffmpeg instalado o arquivo vai com imagem "
            f"junto, o que so e viavel ate ~{_MAX_MINUTOS_SEM_FFMPEG} min. Instale o ffmpeg "
            "(winget install Gyan.FFmpeg) para transcrever videos longos."
        )


def _arquivo_baixado(info: dict, destino: Path) -> Path:
    """Acha o arquivo final, ja depois da conversao para MP3."""
    for pedido in info.get("requested_downloads") or []:
        caminho = pedido.get("filepath") or pedido.get("_filename")
        if caminho and Path(caminho).is_file():
            return Path(caminho)

    # A pasta e exclusiva deste download, entao o maior arquivo dela e o certo.
    arquivos = [p for p in destino.iterdir() if p.is_file()]
    if not arquivos:
        raise MediaError("O download terminou sem gerar arquivo.")
    return max(arquivos, key=lambda p: p.stat().st_size)


def _mime(caminho: Path) -> str:
    mime = _MIME.get(caminho.suffix.lower())
    if not mime:
        raise MediaError(
            f"O site entregou um formato que o Gemini nao le ({caminho.suffix}). "
            "Instale o ffmpeg para converter automaticamente em MP3."
        )
    return mime


def baixar(url: str, destino: Path, progresso: Callable[[str], None] | None = None) -> Media:
    """Baixa a midia do link para `destino` (uma pasta vazia so para isso)."""
    yt_dlp = _yt_dlp()
    com_ffmpeg = tem_ffmpeg()

    def aviso(mensagem: str) -> None:
        if progresso:
            progresso(mensagem)

    opts = _opcoes(destino, com_ffmpeg)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            aviso("Lendo a publicacao...")
            info = _extrair_info(ydl, url)

            duracao = info.get("duration")
            _conferir_duracao(duracao, com_ffmpeg)

            rotulo = "o audio" if com_ffmpeg else "o video"
            aviso(f"Baixando {rotulo}...")
            baixado = ydl.extract_info(info.get("webpage_url") or url, download=True)
            baixado = baixado if isinstance(baixado, dict) else info
    except MediaError:
        raise
    except yt_dlp.utils.DownloadError as exc:
        raise _traduzir_erro(url, str(exc)) from exc
    except Exception as exc:  # extrator quebrado, disco cheio, rede caida
        raise _traduzir_erro(url, str(exc)) from exc

    caminho = _arquivo_baixado(baixado, destino)
    extrator = (baixado.get("extractor_key") or baixado.get("extractor") or "desconhecido").lower()
    titulo = baixado.get("title") or baixado.get("description")
    if isinstance(titulo, str):
        titulo = " ".join(titulo.split())[:120].strip() or None

    return Media(
        path=caminho,
        mime=_mime(caminho),
        source=extrator,
        source_url=baixado.get("webpage_url") or url,
        media_id=str(baixado.get("id") or caminho.stem),
        title=titulo,
        duration=baixado.get("duration") or duracao,
    )
