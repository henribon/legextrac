"""Tipos comuns a qualquer fonte de legenda.

Vive num modulo proprio (sem importar nada do app) porque tanto o caminho do
YouTube quanto o da transcricao por audio produzem estas mesmas estruturas --
e o resto do programa nao precisa saber de onde o texto veio.
"""

from dataclasses import dataclass


class TranscriptError(Exception):
    """Falha esperada ao obter a legenda (mensagem exibivel ao usuario)."""


@dataclass
class Snippet:
    text: str
    start: float
    duration: float


@dataclass
class Transcript:
    video_id: str
    language: str
    language_code: str
    is_generated: bool
    snippets: list[Snippet]
    title: str | None = None
    # De onde veio: "youtube", "instagram", "tiktok"... O nome e o do extrator
    # do yt-dlp, em minusculas.
    source: str = "youtube"
    # Link canonico da publicacao, usado no cabecalho do .txt.
    source_url: str | None = None
    # Como o texto foi obtido: "legenda" (faixa publicada) ou "audio" (ditado
    # pelo modelo). Muda o que da para prometer sobre a precisao dos tempos.
    method: str = "legenda"
