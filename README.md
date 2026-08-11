# legextrac

API em Python que recebe um link do YouTube, extrai a legenda/transcrição do vídeo e traduz para
português usando o DeepL.

## Como funciona

1. `POST /transcript` recebe a URL do vídeo.
2. `youtube-transcript-api` busca **sempre a legenda original**, no idioma falado no vídeo.
3. As linhas são agrupadas em frases — legendas quebram frases no meio, e traduzir fragmentos
   isolados piora bastante o resultado.
4. As frases vão em lotes para o tradutor — **Gemini** por padrão, DeepL como alternativa.
5. Retorna JSON com segmentos + tempos, texto corrido, ou um arquivo `.srt` já traduzido.

### Como a legenda original é identificada

Um vídeo popular pode ter dezenas de legendas traduzidas pela comunidade — o vídeo de teste
(3Blue1Brown) tem 31. Pegar qualquer uma delas significaria traduzir uma tradução. A regra:

1. O YouTube só gera legenda automática (ASR) no idioma do áudio, então a existência dela revela
   qual é o idioma falado.
2. Nesse idioma, se houver legenda escrita por humano, ela vence a ASR — mesmo conteúdo, com
   pontuação e sem erro de transcrição.
3. Se o vídeo não tem ASR (só legenda manual), usa a primeira faixa da lista, que é a faixa padrão
   do vídeo.

Se o vídeo já for falado em português, o tradutor não é chamado e a resposta traz um aviso no
campo `note` — não faz sentido gastar cota traduzindo pt→pt.

## Tradutores

Escolha com `TRANSLATOR` no `.env`.

| | **Gemini** (padrão) | DeepL |
|---|---|---|
| Cota grátis | por requisição (~10–15/min) | 500k caracteres/mês¹ |
| Chave | https://aistudio.google.com/apikey (sem cartão) | https://www.deepl.com/pro-api |
| Vídeos de 1h | dezenas por dia | ~10 por mês |

¹ Fontes de terceiros indicam que o DeepL aposentou os planos API Free/Pro para novos clientes em
julho/2026, migrando para "Developer" (1 milhão de caracteres **no total**, não recorrente). O
changelog oficial não confirma. Verifique no cadastro.

**Por que Gemini como padrão:** a cota é por requisição, não por caractere — como as falas são
agrupadas em lotes de ~60, um vídeo de 1h vira ~12 chamadas. Além disso o modelo enxerga o trecho
inteiro de uma vez, então mantém termos e tom consistentes, coisa que tradutor frase-a-frase erra.

**O risco do Gemini** é ele fundir, dividir ou pular falas — o que arruinaria o sincronismo do
`.srt`. Por isso [gemini.py](app/translators/gemini.py) pede a resposta em JSON com `id` por fala,
confere item a item, e se o alinhamento quebrar reenvia o lote dividido ao meio (um item sozinho é
praticamente impossível de desalinhar). Se nem assim alinhar, a requisição falha com erro claro em
vez de devolver legenda torta.

## Instalação

Requer Python 3.10+.

```bash
python -m venv .venv
```

```bash
.venv\Scripts\Activate.ps1
```

```bash
pip install -r requirements.txt
```

Copie `.env.example` para `.env` e preencha `GEMINI_API_KEY` (chave gratuita, sem cartão, em
https://aistudio.google.com/apikey).

## Rodando

```bash
uvicorn app.main:app --reload
```

Docs interativas: http://127.0.0.1:8000/docs

## Uso

JSON completo (segmentos, tempos, original e tradução):

```bash
curl -X POST http://127.0.0.1:8000/transcript -H "Content-Type: application/json" -d "{\"url\":\"https://www.youtube.com/watch?v=dQw4w9WgXcQ\"}"
```

Só o texto traduzido:

```bash
curl "http://127.0.0.1:8000/transcript?url=https://youtu.be/dQw4w9WgXcQ&format=text"
```

Arquivo de legenda traduzido:

```bash
curl "http://127.0.0.1:8000/transcript?url=https://youtu.be/dQw4w9WgXcQ&format=srt" -o legenda-pt.srt
```

### Parâmetros

| Campo | Padrão | Descrição |
|---|---|---|
| `url` | — | Link `watch`, `youtu.be`, `shorts`, `embed`, `live` ou o ID de 11 caracteres |
| `target_lang` | `PT-BR` | Idioma de destino no formato DeepL (`PT-BR`, `PT-PT`, `EN-US`, …) |
| `translate` | `true` | `false` retorna só a legenda original, sem gastar cota do DeepL |
| `merge_sentences` | `true` | Agrupa linhas em frases antes de traduzir |
| `format` | `json` | `json`, `text` ou `srt` |

### Respostas de erro

- `422` — link inválido, vídeo sem legenda, legendas desativadas, vídeo privado, restrição de
  idade, ou **IP bloqueado pelo YouTube**.
- `502` — falha no tradutor (chave inválida, cota esgotada, rate limit).

O bloqueio de IP acontece depois de muitas requisições seguidas. É temporário: espere alguns
minutos.

## Observações

- **Custo:** um vídeo de 1h costuma ter 40–60 mil caracteres. Use `translate=false` para conferir
  a legenda antes de gastar cota.
- **Privacidade:** no plano gratuito do Gemini, o Google pode usar o conteúdo enviado para
  melhorar os modelos. Se a legenda for sensível, use o DeepL ou um plano pago.
- **Bloqueio de IP:** o YouTube bloqueia IPs de datacenter. Rodando local funciona normalmente;
  se você subir isso numa VPS/nuvem e receber erros de "não foi possível obter a legenda",
  configure `YT_PROXY_HTTP`/`YT_PROXY_HTTPS` no `.env` com um proxy residencial.
- Vídeos sem legenda alguma (nem automática) não têm como ser processados por aqui — precisaria
  baixar o áudio e transcrever com Whisper, que é outro caminho.
