"""Agrupamento de segmentos e geracao de SRT."""

from .youtube import Snippet

_SENTENCE_END = (".", "!", "?", "...", "…", ":")
_MAX_GROUP_CHARS = 500


def merge_into_sentences(snippets: list[Snippet]) -> list[Snippet]:
    """Junta linhas de legenda em frases.

    Legendas do YouTube quebram frases no meio; traduzir fragmento a fragmento
    piora bastante o resultado do DeepL. Agrupar antes de traduzir da contexto
    ao tradutor e mantem o tempo utilizavel (inicio do primeiro trecho ate o
    fim do ultimo).
    """
    merged: list[Snippet] = []
    buffer: list[str] = []
    start = 0.0
    end = 0.0

    for snippet in snippets:
        if not buffer:
            start = snippet.start
        buffer.append(snippet.text)
        end = max(end, snippet.start + snippet.duration)
        joined = " ".join(buffer)
        if joined.rstrip().endswith(_SENTENCE_END) or len(joined) >= _MAX_GROUP_CHARS:
            merged.append(Snippet(text=joined, start=start, duration=max(end - start, 0.0)))
            buffer = []

    if buffer:
        joined = " ".join(buffer)
        merged.append(Snippet(text=joined, start=start, duration=max(end - start, 0.0)))

    return merged


def _timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def to_srt(snippets: list[Snippet], texts: list[str]) -> str:
    """Monta um arquivo SRT a partir dos tempos dos segmentos e dos textos dados."""
    blocks: list[str] = []
    for index, (snippet, text) in enumerate(zip(snippets, texts), start=1):
        start = snippet.start
        end = start + snippet.duration
        # Evita sobreposicao com o proximo bloco.
        if index < len(snippets):
            end = min(end, snippets[index].start)
        if end <= start:
            end = start + 0.5
        blocks.append(f"{index}\n{_timestamp(start)} --> {_timestamp(end)}\n{text}\n")
    return "\n".join(blocks)
