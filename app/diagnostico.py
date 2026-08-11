"""Descobre por que a extracao de legenda falhou.

    python -m app.diagnostico https://www.youtube.com/watch?v=ID

O erro do YouTube e sempre o mesmo generico, mas as causas sao bem diferentes:
video sem legenda, video privado, ou limite de requisicoes por IP. Este script
testa cada camada separadamente e diz qual delas quebrou.
"""

import json
import re
import sys

import httpx

from .youtube import TranscriptError, extract_video_id

_HEADERS = {"Accept-Language": "en-US,en"}


def _ok(texto: str) -> None:
    print(f"  [ok]    {texto}")


def _falha(texto: str) -> None:
    print(f"  [FALHA] {texto}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    try:
        video_id = extract_video_id(sys.argv[1])
    except TranscriptError as exc:
        print(f"URL invalida: {exc}")
        return 1

    print(f"Video: {video_id}")

    # O limite e por IP. Mostrar o IP atual deixa obvio se a troca de rede
    # realmente pegou -- trocar de Wi-Fi nao adianta se o PC continuou saindo
    # pelo cabo, por exemplo.
    try:
        ip = httpx.get("https://api.ipify.org", timeout=15).text.strip()
        print(f"IP publico: {ip}  (anote: precisa mudar ao trocar de rede)\n")
    except httpx.HTTPError:
        print("IP publico: nao foi possivel consultar\n")

    print("1. A pagina do video responde?")
    try:
        pagina = httpx.get(
            f"https://www.youtube.com/watch?v={video_id}",
            timeout=30,
            follow_redirects=True,
            headers=_HEADERS,
        )
    except httpx.HTTPError as exc:
        _falha(f"sem conexao com o YouTube: {exc}")
        return 1

    if pagina.status_code != 200:
        _falha(f"HTTP {pagina.status_code} -- o IP pode estar bloqueado por completo.")
        return 1
    _ok(f"HTTP 200 ({len(pagina.text) // 1024} KB)")

    print("\n2. O video tem legenda?")
    achado = re.search(r'"captionTracks":(\[.*?\])', pagina.text)
    if not achado:
        _falha("nenhuma faixa de legenda na pagina: o video nao tem legenda.")
        return 1

    faixas = json.loads(achado.group(1))
    _ok(f"{len(faixas)} faixa(s)")
    for faixa in faixas[:10]:
        tipo = "automatica" if faixa.get("kind") == "asr" else "humana"
        print(f"          {faixa.get('languageCode'):>6}  {tipo}")
    if len(faixas) > 10:
        print(f"          ... e mais {len(faixas) - 10}")

    print("\n3. O texto da legenda pode ser baixado?")
    try:
        conteudo = httpx.get(faixas[0]["baseUrl"], timeout=30, headers=_HEADERS)
    except httpx.HTTPError as exc:
        _falha(f"erro de rede: {exc}")
        return 1

    if conteudo.status_code == 429:
        _falha("HTTP 429 -- o YouTube esta limitando este IP.")
        print(
            "\nDIAGNOSTICO: limite de requisicoes por IP.\n"
            "  A pagina do video abre normalmente, mas o endpoint da legenda recusa.\n"
            "  Nao tem a ver com a chave do tradutor nem com o video escolhido.\n"
            "  O que fazer: esperar algumas horas, trocar de rede (dados moveis\n"
            "  costumam ter outro IP), ou configurar YT_PROXY_HTTP no .env."
        )
        return 1

    if conteudo.status_code != 200:
        _falha(f"HTTP {conteudo.status_code}")
        return 1

    _ok(f"HTTP 200 ({len(conteudo.text)} bytes)")
    print("\nDIAGNOSTICO: o caminho da legenda esta livre. Pode rodar o testar.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
