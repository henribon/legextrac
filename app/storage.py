"""Gravacao do resultado em arquivo .txt."""

import re
from datetime import datetime
from pathlib import Path

from . import config

# Caracteres proibidos em nome de arquivo no Windows.
_INVALID = r'[<>:"/\\|?*\x00-\x1f]'

# Nomes de dispositivo reservados: um arquivo "CON.txt" nao pode ser criado.
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

_MAX_STEM = 120


def sanitize(name: str) -> str:
    """Transforma um titulo de video em nome de arquivo valido no Windows."""
    name = re.sub(_INVALID, "", name)
    name = " ".join(name.split())
    # O Windows recusa nome terminado em ponto ou espaco.
    name = name.rstrip(". ")
    if len(name) > _MAX_STEM:
        name = name[:_MAX_STEM].rstrip(". ")
    if name.split(".")[0].upper() in _RESERVED:
        name = f"_{name}"
    return name or "video"


def downloads_dir() -> Path:
    """A pasta Downloads real do usuario.

    O caminho pode ter sido movido pelo usuario (para outro disco, OneDrive...),
    entao o registro do Windows e a fonte confiavel; ~/Downloads e so o plano B.
    """
    try:
        import winreg

        chave = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave) as k:
            valor, _ = winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")
            caminho = Path(valor)
            if caminho.is_dir():
                return caminho
    except Exception:
        pass
    return Path.home() / "Downloads"


def output_dir(destino: Path | None = None) -> Path:
    if destino is not None:
        path = Path(destino).expanduser()
    elif config.OUTPUT_DIR:
        path = Path(config.OUTPUT_DIR).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
    else:
        path = downloads_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_txt(
    lines: list[str],
    video_id: str,
    title: str | None,
    source_language: str,
    source_language_code: str,
    target_lang: str | None,
    translated: bool,
    destino: Path | None = None,
) -> Path:
    """Grava uma frase por linha e devolve o caminho do arquivo.

    Reexecutar o mesmo video sobrescreve o arquivo, em vez de acumular copias.
    """
    stem = sanitize(f"{title} [{video_id}]" if title else video_id)
    destino = output_dir(destino) / f"{stem}.txt"

    cabecalho = [
        f"Titulo: {title}" if title else f"Video: {video_id}",
        f"Link: https://www.youtube.com/watch?v={video_id}",
        f"Idioma original: {source_language} ({source_language_code})",
        f"Traduzido para: {target_lang}" if translated else "Sem traducao (texto original)",
        f"Gerado em: {datetime.now():%d/%m/%Y %H:%M}",
        "-" * 60,
        "",
    ]

    # utf-8-sig: o BOM evita acentos quebrados ao abrir no Bloco de Notas
    # e no Excel, que e onde esse .txt normalmente vai parar no Windows.
    destino.write_text("\n".join(cabecalho + lines) + "\n", encoding="utf-8-sig")
    return destino
