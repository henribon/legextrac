"""Gera o executavel autonomo em dist/legextrac.exe.

    .venv\\Scripts\\python.exe compilar.py

Depois rode `python instalar.py` para copiar o exe para fora do projeto e
atualizar o atalho do menu Iniciar.
"""

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

COMANDO = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--onefile",
    "--windowed",  # sem janela de console atras
    "--clean",
    "--name",
    "legextrac",
    "--icon",
    str(RAIZ / "assets" / "legextrac.ico"),
    # O PyInstaller nao enxerga imports feitos de forma indireta.
    "--hidden-import=youtube_transcript_api",
    "--hidden-import=defusedxml.ElementTree",
    # A API web nao faz parte do app; fora dela o exe fica bem menor.
    "--exclude-module=fastapi",
    "--exclude-module=uvicorn",
    "--exclude-module=starlette",
    "--exclude-module=PyInstaller",
    str(RAIZ / "legextrac.py"),
]


def main() -> int:
    if not (RAIZ / "assets" / "legextrac.ico").exists():
        print("Icone ausente. Rode 'python instalar.py' antes para gera-lo.")
        return 1

    print("Compilando (leva um ou dois minutos)...\n")
    resultado = subprocess.run(COMANDO, cwd=RAIZ)
    if resultado.returncode != 0:
        return resultado.returncode

    exe = RAIZ / "dist" / "legextrac.exe"
    tamanho = exe.stat().st_size / (1024 * 1024)
    print(f"\nPronto: {exe}  ({tamanho:.1f} MB)")
    print("Agora rode: python instalar.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
