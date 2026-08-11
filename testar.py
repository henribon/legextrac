"""Teste rapido da API: troque o link abaixo e rode.

    python testar.py

Tambem aceita o link como argumento:

    python testar.py https://youtu.be/OUTRO_VIDEO
"""

import sys
import time

import httpx

# ---------------------------------------------------------------------------
VIDEO = "https://www.youtube.com/watch?v=aircAruvnKk"  # <<< TROQUE O LINK AQUI
# ---------------------------------------------------------------------------

API = "http://127.0.0.1:8000"
LARGURA = 100


def linha(titulo: str = "") -> None:
    print(f"\n{titulo}\n{'-' * LARGURA}" if titulo else "-" * LARGURA)


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else VIDEO

    try:
        saude = httpx.get(f"{API}/health", timeout=5).json()
    except httpx.HTTPError:
        print("A API nao esta respondendo em " + API)
        print("Suba o servidor primeiro:")
        print(r"   .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000")
        return 1

    print(f"Tradutor: {saude['translator']} ({saude.get('model') or '-'})")
    if not saude["translator_configured"]:
        print("AVISO: chave do tradutor nao configurada; use translate=false ou preencha o .env.")

    print(f"Video:   {url}")
    print("\nBuscando legenda e traduzindo (pode levar alguns minutos)...")

    inicio = time.monotonic()
    try:
        resposta = httpx.post(f"{API}/transcript", json={"url": url}, timeout=900)
    except httpx.HTTPError as exc:
        print(f"Falha na chamada: {exc}")
        return 1
    duracao = time.monotonic() - inicio

    if resposta.status_code != 200:
        print(f"\nERRO {resposta.status_code}: {resposta.json().get('detail')}")
        return 1

    dados = resposta.json()
    linha("RESULTADO")
    print(f"Titulo:          {dados['title'] or '(sem titulo)'}")
    print(f"Idioma original: {dados['source_language']} ({dados['source_language_code']})")
    print(f"Legenda:         {'automatica' if dados['is_generated'] else 'feita por humano'}")
    print(f"Segmentos:       {dados['segment_count']}")
    print(f"Traduzido:       {dados['translated']} -> {dados['target_lang']}")
    if dados.get("note"):
        print(f"Observacao:      {dados['note']}")
    print(f"Tempo:           {duracao:.1f}s")
    print(f"Arquivo:         {dados['saved_to']}")

    linha("AMOSTRA (primeiros 5 segmentos)")
    for segmento in dados["segments"][:5]:
        minutos, segundos = divmod(int(segmento["start"]), 60)
        print(f"[{minutos:02d}:{segundos:02d}]")
        print(f"  original: {segmento['text']}")
        print(f"  traduzido: {segmento['translated_text'] or '(sem traducao)'}")

    linha()
    print(f"Abra o arquivo completo em:\n  {dados['saved_to']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
