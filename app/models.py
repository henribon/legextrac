"""Schemas de entrada e saida da API."""

from typing import Literal

from pydantic import BaseModel, Field


class TranscriptRequest(BaseModel):
    url: str = Field(
        ...,
        description=(
            "Link de qualquer publicacao com video ou audio: YouTube, Instagram, TikTok, "
            "X, Facebook, Vimeo, Reddit... ou o ID de 11 caracteres do YouTube"
        ),
        examples=[
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.instagram.com/reel/CxxxxxxxxxX/",
            "https://www.tiktok.com/@usuario/video/7300000000000000000",
        ],
    )
    target_lang: str | None = Field(
        default=None,
        description="Idioma de destino no formato DeepL. Padrao: PT-BR",
        examples=["PT-BR", "PT-PT"],
    )
    translate: bool = Field(
        default=True,
        description="Se false, retorna apenas a legenda original sem chamar o DeepL",
    )
    merge_sentences: bool = Field(
        default=True,
        description=(
            "Junta as linhas da legenda em frases antes de traduzir. "
            "Melhora muito a qualidade do DeepL; desligue para manter o corte original."
        ),
    )
    save: bool = Field(
        default=True,
        description="Grava o resultado em .txt na pasta configurada em OUTPUT_DIR",
    )
    format: Literal["json", "text", "srt"] = Field(
        default="json",
        description="json = segmentos + texto; text = texto corrido; srt = arquivo de legenda",
    )


class Segment(BaseModel):
    start: float
    duration: float
    text: str
    translated_text: str | None = None


class TranscriptResponse(BaseModel):
    video_id: str
    title: str | None = None
    saved_to: str | None = None
    source: str = Field(default="youtube", description="Plataforma de onde veio a midia")
    source_url: str | None = Field(default=None, description="Link canonico da publicacao")
    method: str = Field(
        default="legenda",
        description=(
            "Como o texto foi obtido: 'legenda' (faixa publicada, tempos exatos) "
            "ou 'audio' (ditado pelo Gemini, tempos aproximados)"
        ),
    )
    source_language: str
    source_language_code: str
    is_generated: bool
    target_lang: str | None
    translated: bool
    note: str | None = None
    segment_count: int
    text: str
    translated_text: str | None = None
    segments: list[Segment]
