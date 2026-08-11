"""API: recebe um link do YouTube, extrai a legenda original e traduz."""

from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse

from . import config, pipeline, translators
from .formats import to_srt
from .models import Segment, TranscriptRequest, TranscriptResponse

app = FastAPI(
    title="legextrac",
    description="Extrai a legenda original de videos do YouTube e traduz para portugues.",
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
        r = pipeline.processar(
            url=req.url,
            target_lang=req.target_lang,
            translate=req.translate,
            merge_sentences=req.merge_sentences,
            save=req.save,
        )
    except pipeline.PipelineError as exc:
        # 422 para problema com o video/legenda, 502 quando o tradutor falhou.
        codigo = 502 if "Gemini" in str(exc) or "DeepL" in str(exc) else 422
        raise HTTPException(status_code=codigo, detail=str(exc)) from exc

    saved_to = str(r.saved_to) if r.saved_to else None

    # Cabecalho HTTP so aceita latin-1, e o caminho pode ter acento vindo do
    # titulo do video. Vai percent-encoded; o corpo JSON leva o caminho cru.
    headers = {"X-Saved-To": quote(saved_to)} if saved_to else None

    if req.format == "srt":
        return PlainTextResponse(
            to_srt(r.snippets, r.textos),
            media_type="application/x-subrip; charset=utf-8",
            headers=headers,
        )
    if req.format == "text":
        return PlainTextResponse(
            " ".join(r.textos),
            media_type="text/plain; charset=utf-8",
            headers=headers,
        )

    return TranscriptResponse(
        video_id=r.video_id,
        title=r.title,
        saved_to=saved_to,
        source_language=r.source_language,
        source_language_code=r.source_language_code,
        is_generated=r.is_generated,
        target_lang=r.target_lang,
        translated=r.translated,
        note=r.note,
        segment_count=len(r.snippets),
        text=" ".join(r.originais),
        translated_text=" ".join(r.traducoes) if r.traducoes is not None else None,
        segments=[
            Segment(
                start=round(s.start, 3),
                duration=round(s.duration, 3),
                text=s.text,
                translated_text=r.traducoes[i] if r.traducoes is not None else None,
            )
            for i, s in enumerate(r.snippets)
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
    save: bool = Query(default=True),
    format: str = Query(default="json", pattern="^(json|text|srt)$"),
):
    return _process(
        TranscriptRequest(
            url=url,
            target_lang=target_lang,
            translate=translate,
            save=save,
            merge_sentences=merge_sentences,
            format=format,  # type: ignore[arg-type]
        )
    )
