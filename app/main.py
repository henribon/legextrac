"""API: recebe um link do YouTube, extrai a legenda e traduz com o DeepL."""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse

from . import config, translators
from .formats import merge_into_sentences, to_srt
from .models import Segment, TranscriptRequest, TranscriptResponse
from .youtube import TranscriptError, fetch_transcript

app = FastAPI(
    title="legextrac",
    description="Extrai legendas de videos do YouTube e traduz para portugues via DeepL.",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "translator": config.TRANSLATOR,
        "translator_configured": translators.is_configured(),
        "model": config.GEMINI_MODEL if config.TRANSLATOR == "gemini" else None,
    }


def _process(req: TranscriptRequest):
    try:
        transcript = fetch_transcript(req.url)
    except TranscriptError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    snippets = (
        merge_into_sentences(transcript.snippets)
        if req.merge_sentences
        else transcript.snippets
    )
    originals = [s.text for s in snippets]

    translations: list[str] | None = None
    note: str | None = None
    target = None
    if req.translate:
        target = (req.target_lang or config.DEFAULT_TARGET_LANG).upper()
        source = transcript.language_code.split("-")[0].lower()
        if source == target.split("-")[0].lower():
            # Video ja falado no idioma de destino: traduzir gastaria cota a toa.
            note = f"Legenda original ja esta em {transcript.language}; DeepL nao foi chamado."
        else:
            try:
                translations = translators.translate(
                    originals,
                    target_lang=target,
                    source_lang=transcript.language_code,
                )
            except translators.TranslationError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc

    final_texts = translations if translations is not None else originals

    if req.format == "srt":
        return PlainTextResponse(
            to_srt(snippets, final_texts),
            media_type="application/x-subrip; charset=utf-8",
        )
    if req.format == "text":
        return PlainTextResponse(" ".join(final_texts), media_type="text/plain; charset=utf-8")

    return TranscriptResponse(
        video_id=transcript.video_id,
        source_language=transcript.language,
        source_language_code=transcript.language_code,
        is_generated=transcript.is_generated,
        target_lang=target,
        translated=translations is not None,
        note=note,
        segment_count=len(snippets),
        text=" ".join(originals),
        translated_text=" ".join(translations) if translations is not None else None,
        segments=[
            Segment(
                start=round(s.start, 3),
                duration=round(s.duration, 3),
                text=s.text,
                translated_text=translations[i] if translations is not None else None,
            )
            for i, s in enumerate(snippets)
        ],
    )


@app.post("/transcript", response_model=None, summary="Extrai e traduz a legenda")
def transcript(req: TranscriptRequest):
    return _process(req)


@app.get("/transcript", response_model=None, summary="Mesma coisa, via query string")
def transcript_get(
    url: str = Query(..., description="Link do video no YouTube"),
    target_lang: str | None = Query(default=None),
    translate: bool = Query(default=True),
    merge_sentences: bool = Query(default=True),
    format: str = Query(default="json", pattern="^(json|text|srt)$"),
):
    return _process(
        TranscriptRequest(
            url=url,
            target_lang=target_lang,
            translate=translate,
            merge_sentences=merge_sentences,
            format=format,  # type: ignore[arg-type]
        )
    )
