"""Cria o icone e o atalho do app no menu Iniciar.

    .venv\\Scripts\\python.exe instalar.py

Depois e so procurar por "legextrac" no Iniciar, clicar com o botao direito e
escolher "Fixar em Iniciar".
"""

import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ASSETS = RAIZ / "assets"
ICONE = ASSETS / "legextrac.ico"
NOME = "legextrac"

LADO = 64
FUNDO = (0x4C, 0x7F, 0xE8)  # azul, em RGB
BARRA = (0xFF, 0xFF, 0xFF)
RAIO = 13


def _desenhar() -> list[list[tuple[int, int, int, int]]]:
    """Quadrado azul de cantos arredondados com tres barras de legenda."""
    vazio = (0, 0, 0, 0)
    px = [[vazio for _ in range(LADO)] for _ in range(LADO)]

    for y in range(LADO):
        for x in range(LADO):
            # Cantos: so pinta o que estiver dentro do raio.
            cx = RAIO - 1 if x < RAIO else (LADO - RAIO if x >= LADO - RAIO else x)
            cy = RAIO - 1 if y < RAIO else (LADO - RAIO if y >= LADO - RAIO else y)
            if (x - cx) ** 2 + (y - cy) ** 2 > RAIO**2:
                continue
            px[y][x] = (FUNDO[2], FUNDO[1], FUNDO[0], 255)  # BGRA

    # Tres barras de larguras diferentes, como linhas de legenda.
    for topo, inicio, fim in ((21, 12, 52), (34, 12, 44), (47, 12, 36)):
        for y in range(topo, topo + 7):
            for x in range(inicio, fim):
                px[y][x] = (BARRA[2], BARRA[1], BARRA[0], 255)

    return px


def gerar_icone() -> Path:
    ASSETS.mkdir(exist_ok=True)
    px = _desenhar()

    # Dados XOR: linhas de baixo para cima, formato BGRA.
    corpo = bytearray()
    for y in range(LADO - 1, -1, -1):
        for x in range(LADO):
            corpo += bytes(px[y][x])

    # Mascara AND zerada: a transparencia real vem do canal alfa.
    mascara = bytes((LADO // 8) * LADO)

    cabecalho_bmp = struct.pack(
        "<IiiHHIIiiII", 40, LADO, LADO * 2, 1, 32, 0, len(corpo) + len(mascara), 0, 0, 0, 0
    )
    imagem = cabecalho_bmp + bytes(corpo) + mascara

    ico = struct.pack("<HHH", 0, 1, 1) + struct.pack(
        "<BBBBHHII", LADO, LADO, 0, 0, 1, 32, len(imagem), 22
    )
    ICONE.write_bytes(ico + imagem)
    return ICONE


def instalar_exe() -> Path | None:
    """Copia o .exe compilado para uma pasta fixa, fora do projeto.

    E isso que deixa o app independente: depois disso a pasta de
    desenvolvimento pode ser movida ou apagada sem quebrar o atalho.
    """
    origem = RAIZ / "dist" / f"{NOME}.exe"
    if not origem.exists():
        return None

    destino_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / NOME
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / f"{NOME}.exe"
    shutil.copy2(origem, destino)
    return destino


def preparar_config() -> Path:
    """Garante um .env na pasta de configuracao do usuario.

    O .exe pode estar em qualquer lugar, entao ele nao tem como achar o .env
    do projeto. A chave fica aqui -- fora do executavel, que assim pode ser
    copiado para outra maquina sem levar segredo junto.
    """
    from app.config import PASTA_CONFIG

    PASTA_CONFIG.mkdir(parents=True, exist_ok=True)
    destino = PASTA_CONFIG / ".env"
    if not destino.exists():
        origem = RAIZ / ".env"
        if origem.exists():
            shutil.copy2(origem, destino)
        else:
            shutil.copy2(RAIZ / ".env.example", destino)
    return destino


def criar_atalho(alvo: Path | None) -> Path:
    if alvo is not None:  # .exe autonomo
        target, args, pasta = str(alvo), "", str(alvo.parent)
    else:  # roda pelo Python do projeto
        pythonw = RAIZ / ".venv" / "Scripts" / "pythonw.exe"
        if not pythonw.exists():
            raise SystemExit(
                f"Nao encontrei {pythonw}.\n"
                "Crie o ambiente virtual antes: python -m venv .venv"
            )
        target, args, pasta = str(pythonw), "-m app.gui", str(RAIZ)

    iniciar = (
        Path.home()
        / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs"
        / f"{NOME}.lnk"
    )

    # WScript.Shell e o jeito nativo de criar .lnk sem dependencia extra.
    script = f"""
$atalho = (New-Object -ComObject WScript.Shell).CreateShortcut('{iniciar}')
$atalho.TargetPath = '{target}'
$atalho.Arguments = '{args}'
$atalho.WorkingDirectory = '{pasta}'
$atalho.IconLocation = '{ICONE if alvo is None else alvo}'
$atalho.Description = 'Transcreve e traduz legendas do YouTube'
$atalho.Save()
"""
    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        raise SystemExit(f"Falha ao criar o atalho:\n{resultado.stderr}")
    return iniciar


def main() -> int:
    print(f"Icone:   {gerar_icone()}")

    exe = instalar_exe()
    if exe:
        print(f"App:     {exe}  (autonomo)")
    else:
        print("App:     rodando pelo Python do projeto")
        print("         (para gerar o .exe: python compilar.py)")

    print(f"Config:  {preparar_config()}")
    print(f"Atalho:  {criar_atalho(exe)}")
    print(
        "\nPronto.\n"
        "  1. Abra o Iniciar e digite 'legextrac'\n"
        "  2. Clique com o botao direito no resultado\n"
        "  3. Escolha 'Fixar em Iniciar' (ou 'Fixar na barra de tarefas')\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
