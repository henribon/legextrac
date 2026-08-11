"""Lista os modelos Gemini que a sua chave alcanca.

    python -m app.models_disponiveis

Serve para quando o Google aposenta um modelo e a API passa a responder 404:
a lista mostra o que colocar em GEMINI_MODEL no .env.
"""

import sys

import httpx

from . import config


def main() -> int:
    if not config.GEMINI_API_KEY:
        print("GEMINI_API_KEY nao configurada no .env.")
        return 1

    try:
        response = httpx.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": config.GEMINI_API_KEY},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        print(f"Falha de rede: {exc}")
        return 1

    if response.status_code != 200:
        print(f"Erro {response.status_code}: {response.text[:300]}")
        return 1

    print(f"Modelo em uso: {config.GEMINI_MODEL}\n")
    print("Modelos que aceitam geracao de texto:")
    for model in response.json().get("models", []):
        if "generateContent" in model.get("supportedGenerationMethods", []):
            nome = model["name"].removeprefix("models/")
            print(f"  {nome:38} {model.get('displayName', '')}")
    print("\nNem todo modelo listado tem cota no plano gratuito;")
    print("um 429 significa cota esgotada, nao modelo invalido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
