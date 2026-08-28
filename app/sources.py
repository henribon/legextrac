"""Decide de onde tirar o texto de um link, e devolve sempre a mesma coisa.

Dois caminhos, nesta ordem de preferencia:

1. **Legenda publicada** -- so o YouTube tem. E de graca, instantanea e com os
   tempos exatos do video, entao ganha sempre que existir.
2. **Audio ditado pelo Gemini** -- para todo o resto (Instagram, TikTok, X,
   Facebook, Vimeo, Reddit e as centenas de sites que o yt-dlp conhece), e
   tambem para video do YouTube sem legenda ou com o IP limitado.

O resto do programa so ve o `Transcript` que sai daqui e nao precisa saber por
qual dos dois caminhos ele veio.
"""

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from . import config, media, speech, youtube
from .transcript import Transcript, TranscriptError


def _por_audio(url: str, progresso: Callable[[str], None] | None) -> Transcript:
    """Baixa a midia numa pasta temporaria e dita o audio."""
    pasta = Path(tempfile.mkdtemp(prefix="legextrac-"))
    try:
        arquivo = media.baixar(url, pasta, progresso=progresso)
        return speech.transcrever(arquivo, progresso=progresso)
    finally:
        # O arquivo pode ter dezenas de MB; nao ha motivo para ele sobreviver.
        shutil.rmtree(pasta, ignore_errors=True)


def fetch_transcript(
    url: str, progresso: Callable[[str], None] | None = None
) -> Transcript:
    """Obtem a legenda do link, no idioma original em que foi falado."""
    url = (url or "").strip()
    if not url:
        raise TranscriptError("URL vazia.")

    def aviso(mensagem: str) -> None:
        if progresso:
            progresso(mensagem)

    motivo: str | None = None

    if youtube.is_youtube(url):
        aviso("Buscando a legenda no YouTube...")
        try:
            return youtube.fetch_captions(url)
        except youtube.SemLegenda as exc:
            # Video sem legenda ou IP limitado: da para contornar ouvindo o
            # audio. Video privado ou com restricao de idade nao cai aqui,
            # porque nem o download funcionaria.
            if not config.AUDIO_FALLBACK:
                raise
            motivo = str(exc)
            aviso("Sem legenda pronta no YouTube; vou transcrever pelo audio.")

    try:
        return _por_audio(url, progresso)
    except TranscriptError as exc:
        if motivo:
            raise TranscriptError(f"{motivo}\n\nPelo audio tambem nao deu: {exc}") from exc
        raise
