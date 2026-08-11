"""O fluxo completo: buscar legenda -> agrupar -> traduzir -> gravar.

Fica separado da API porque o aplicativo de desktop usa exatamente o mesmo
caminho, sem HTTP no meio.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import config, storage, translators
from .formats import merge_into_sentences
from .youtube import Snippet, TranscriptError, fetch_transcript


class PipelineError(Exception):
    """Falha esperada, com mensagem pronta para mostrar ao usuario."""


@dataclass
class Resultado:
    video_id: str
    title: str | None
    source_language: str
    source_language_code: str
    is_generated: bool
    target_lang: str | None
    translated: bool
    note: str | None
    snippets: list[Snippet]
    originais: list[str]
    traducoes: list[str] | None
    saved_to: Path | None = None
    _final: list[str] = field(default_factory=list)

    @property
    def textos(self) -> list[str]:
        """O texto que interessa: traduzido quando houve traducao."""
        return self.traducoes if self.traducoes is not None else self.originais


def processar(
    url: str,
    target_lang: str | None = None,
    translate: bool = True,
    merge_sentences: bool = True,
    save: bool = True,
    output_dir: Path | None = None,
    progresso: Callable[[str], None] | None = None,
) -> Resultado:
    """Roda o fluxo inteiro.

    `progresso` recebe mensagens curtas de status; a interface grafica usa isso
    para nao parecer travada durante a traducao, que e a etapa demorada.
    """

    def aviso(mensagem: str) -> None:
        if progresso:
            progresso(mensagem)

    aviso("Buscando a legenda no YouTube...")
    try:
        transcript = fetch_transcript(url)
    except TranscriptError as exc:
        raise PipelineError(str(exc)) from exc

    snippets = (
        merge_into_sentences(transcript.snippets) if merge_sentences else transcript.snippets
    )
    originais = [s.text for s in snippets]
    aviso(f"Legenda em {transcript.language}: {len(snippets)} frases.")

    traducoes: list[str] | None = None
    note: str | None = None
    target: str | None = None

    if translate:
        target = (target_lang or config.DEFAULT_TARGET_LANG).upper()
        origem = transcript.language_code.split("-")[0].lower()
        if origem == target.split("-")[0].lower():
            note = f"O video ja esta em {transcript.language}; nao foi traduzido."
            aviso(note)
        else:
            aviso(f"Traduzindo {len(originais)} frases para {target}...")
            try:
                traducoes = translators.translate(
                    originais, target_lang=target, source_lang=transcript.language_code
                )
            except translators.TranslationError as exc:
                raise PipelineError(str(exc)) from exc

    resultado = Resultado(
        video_id=transcript.video_id,
        title=transcript.title,
        source_language=transcript.language,
        source_language_code=transcript.language_code,
        is_generated=transcript.is_generated,
        target_lang=target,
        translated=traducoes is not None,
        note=note,
        snippets=snippets,
        originais=originais,
        traducoes=traducoes,
    )

    if save:
        aviso("Gravando o arquivo...")
        try:
            resultado.saved_to = storage.save_txt(
                lines=resultado.textos,
                video_id=resultado.video_id,
                title=resultado.title,
                source_language=resultado.source_language,
                source_language_code=resultado.source_language_code,
                target_lang=target,
                translated=resultado.translated,
                destino=output_dir,
            )
        except OSError as exc:
            raise PipelineError(f"Nao foi possivel gravar o arquivo: {exc}") from exc

    return resultado
