# legextrac

API em Python que recebe o link de qualquer publicação com vídeo ou áudio — YouTube, Instagram,
TikTok, X, Facebook, Vimeo, Reddit e as centenas de sites que o `yt-dlp` conhece — extrai a fala no
idioma original e traduz para português.

## Como funciona

1. `POST /transcript` recebe a URL.
2. O texto vem por um de dois caminhos, nessa ordem de preferência:
   - **Legenda publicada** (só o YouTube): `youtube-transcript-api` busca **sempre a legenda
     original**, no idioma falado no vídeo. É de graça, instantânea e com os tempos exatos.
   - **Áudio ditado pelo Gemini** (todo o resto): o `yt-dlp` baixa a mídia e o mesmo modelo que já
     traduz transcreve a fala. Vale também para vídeo do YouTube sem legenda.
3. As linhas são agrupadas em frases — legendas quebram frases no meio, e traduzir fragmentos
   isolados piora bastante o resultado.
4. As frases vão em lotes para o tradutor — **Gemini** por padrão, DeepL como alternativa.
5. Grava um `.txt` com a tradução na pasta **Downloads** (configurável em `OUTPUT_DIR`).
6. Retorna JSON com segmentos + tempos, texto corrido, ou um arquivo `.srt` já traduzido.

## Arquivo gerado

Cada execução grava um `.txt` na pasta **Downloads**, nomeado com o título do vídeo e o ID:

```
C:\Users\voce\Downloads\But what is a neural network [aircAruvnKk].txt
```

Para gravar em outro lugar, defina `OUTPUT_DIR` no `.env` (aceita caminho absoluto ou relativo à
raiz do projeto). O caminho real da pasta Downloads vem do registro do Windows, então funciona
mesmo se você a moveu para outro disco ou para o OneDrive.

Uma frase por linha, com cabeçalho de contexto:

```
Titulo: But what is a neural network?
Link: https://www.youtube.com/watch?v=aircAruvnKk
Fonte: YouTube (legenda publicada no site)
Idioma original: English (en)
Traduzido para: PT-BR
Gerado em: 11/08/2026 09:28
------------------------------------------------------------

Isto é um 3.
Está escrito de forma desleixada, mas seu cérebro lê sem dificuldade.
```

Detalhes:

- A linha `Fonte:` diz de qual plataforma veio e se o texto é legenda publicada ou ditada do
  áudio — o que muda o que dá para esperar da precisão dos tempos.
- O título vem do oEmbed público do YouTube (ou dos metadados do `yt-dlp`, nos outros sites). Se
  essa chamada falhar, o arquivo fica só com o ID — não é motivo para a requisição inteira falhar.
- Caracteres proibidos pelo Windows (`\ / : * ? " < > |`) são removidos, e nomes reservados
  (`CON`, `NUL`, `COM1`…) ganham prefixo, senão o Windows recusa criar o arquivo.
- Gravado em UTF-8 com BOM, para não sair com acento quebrado no Bloco de Notas.
- Rodar o mesmo vídeo de novo **sobrescreve** o arquivo, em vez de acumular cópias.
- `save=false` desliga a gravação. Nos formatos `text` e `srt`, o caminho volta no cabeçalho
  HTTP `X-Saved-To` (percent-encoded, porque cabeçalho não aceita acento).

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

## Instagram, TikTok e outros sites

Fora do YouTube praticamente ninguém publica faixa de legenda — só existe o vídeo. Para esses
links o caminho é outro: o `yt-dlp` baixa a mídia e o **Gemini transcreve o áudio**.

Reaproveita a `GEMINI_API_KEY` que já está no `.env` (mesmo com `TRANSLATOR=deepl`), então não
entra chave nova nem modelo local pesado. O que muda em relação ao YouTube:

| | Legenda publicada (YouTube) | Áudio ditado (resto) |
|---|---|---|
| Custo | zero | cota do Gemini |
| Tempo | instantâneo | download + ~10–60 s de transcrição |
| Tempos do `.srt` | exatos | aproximados, ditados pelo modelo |
| Precisão | a que o autor publicou | boa, mas o modelo pode errar nome próprio |

### ffmpeg (recomendado)

Com o `ffmpeg` no PATH, só a trilha de **áudio** é baixada e convertida para MP3: arquivo pequeno e
cobrança de tokens ~8x menor. Sem ele, o programa baixa o MP4 inteiro e manda vídeo junto — o que
funciona, mas fica limitado a uns 12 minutos por vídeo.

```bash
winget install Gyan.FFmpeg
```

O `/health` da API mostra se ele foi encontrado. Com `ffmpeg` o teto passa a ser o
`MEDIA_MAX_MINUTES` (padrão 30 min).

### Conteúdo que exige login

Instagram e TikTok escondem boa parte das publicações atrás de login, e aí o download falha com
uma mensagem pedindo cookies. A saída é reaproveitar a sessão já aberta no seu navegador:

```
COOKIES_FROM_BROWSER=chrome
```

Aceita `chrome`, `edge`, `firefox`, `brave`, `opera`, `vivaldi`, `safari` e o formato
`chrome:Profile 2` para escolher o perfil. Como alternativa, exporte um `cookies.txt` no formato
Netscape e aponte `COOKIES_FILE` para ele — esse tem prioridade.

Feche o navegador antes de rodar: com o Chrome aberto o arquivo de cookies fica travado no Windows.

### YouTube sem legenda

Vídeo do YouTube que não tem legenda nenhuma — ou cujo IP levou 429 no endpoint de legendas —
também cai no caminho do áudio, em vez de simplesmente falhar. Para preferir o erro e não gastar
cota, `AUDIO_FALLBACK=0` no `.env`.

### Site novo, extrator quebrado

Quando um site muda, o extrator correspondente para de funcionar até o `yt-dlp` ser atualizado.
É a manutenção normal dessa biblioteca:

```bash
pip install -U yt-dlp
```

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

### Modelos

O Google aposenta modelos com frequência — um modelo que sumiu responde **404**, e a mensagem de
erro já diz o que fazer. Para ver o que a sua chave alcança:

```bash
python -m app.models_disponiveis
```

Ajuste `GEMINI_MODEL` no `.env`. Padrão: `gemini-3.5-flash`. Se aparecer **429** (cota esgotada,
não modelo inválido), troque para `gemini-3.5-flash-lite`, que tem cota mais folgada.

Detalhe de implementação: o campo que reduz o "thinking" mudou de nome entre gerações de modelo
(`thinkingBudget` no 2.x, `thinkingLevel` no 3.x). Se o modelo recusar o campo com 400, a chamada
repete sem ele automaticamente.

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

Para links fora do YouTube, instale também o `ffmpeg` — opcional, mas deixa a transcrição muito
mais barata e permite vídeos longos:

```bash
winget install Gyan.FFmpeg
```

### Onde guardar a chave

O `.env` está no `.gitignore`, então **não vai para o repositório** — é o padrão da indústria, e o
`.env.example` (esse sim versionado) documenta quais variáveis existem, sem os valores.

Se quiser a chave fora da pasta do projeto, defina uma variável de usuário do Windows:

```bash
setx GEMINI_API_KEY "sua-chave"
```

Variável de ambiente tem precedência sobre o `.env` (o `load_dotenv` não sobrescreve o que já
existe), então basta apagar a linha do `.env`. Abra um terminal novo para o `setx` valer.

No VS Code, `.vscode/settings.json` e `.vscode/launch.json` já apontam para o `.env` — só apertar
F5 para subir a API com debugger. Esses dois arquivos não contêm segredo, só o caminho.

## Aplicativo (janela)

A forma mais simples de usar. Gere o executável e instale:

```bash
python compilar.py
```

```bash
python instalar.py
```

Depois procure por **legextrac** no Iniciar, clique com o botão direito e escolha **Fixar em
Iniciar**.

O que o `instalar.py` faz:

| | |
|---|---|
| `%LOCALAPPDATA%\Programs\legextrac\legextrac.exe` | o app, ~30 MB, sem depender do projeto |
| `%APPDATA%\legextrac\.env` | a chave da API, fora do executável |
| Menu Iniciar `legextrac.lnk` | o atalho, com ícone |

Depois disso a pasta do projeto pode ser movida ou apagada — o app continua funcionando. Se o
`.exe` ainda não tiver sido compilado, o `instalar.py` cria o atalho apontando para o Python do
projeto, que funciona igual mas depende da pasta.

**A chave fica fora do `.exe`**, em `%APPDATA%\legextrac\.env`. Isso é de propósito: o executável
pode ser copiado para outra máquina sem levar segredo junto — lá, basta criar o `.env` na mesma
pasta de configuração. A busca é em ordem: pasta atual, pasta do executável, `%APPDATA%\legextrac`.
Variável de ambiente do sistema tem prioridade sobre todas.

A janela tem um campo para o link e o botão **TRANSCREVER**. Aceita link de qualquer site
suportado. Ao terminar, o arquivo é salvo na pasta **Downloads** e o Explorer abre com ele já
selecionado.

Detalhes:

- Se você copiou qualquer link antes de abrir o app, o campo já vem preenchido.
- `Enter` transcreve, `Esc` fecha.
- O trabalho roda em outra thread, então a janela não congela durante a tradução.
- Roda com `pythonw.exe`, sem janela preta de console atrás.
- Não precisa de servidor: o app chama o mesmo pipeline que a API usa.

Para abrir sem o atalho:

```bash
.venv\Scripts\pythonw.exe -m app.gui
```

## API (opcional)

```bash
uvicorn app.main:app --reload
```

Docs interativas: http://127.0.0.1:8000/docs

### Teste rápido

Abra [testar.py](testar.py), troque o link na linha marcada e rode:

```bash
python testar.py
```

Ou passe o link direto, sem editar nada:

```bash
python testar.py https://youtu.be/SEU_VIDEO
```

Ele mostra título, idioma detectado, tempo, o caminho do `.txt` gerado e os primeiros segmentos
com original e tradução lado a lado.

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

Um reel do Instagram (mesma chamada; o caminho do áudio é escolhido sozinho):

```bash
curl -X POST http://127.0.0.1:8000/transcript -H "Content-Type: application/json" -d "{\"url\":\"https://www.instagram.com/reel/CxxxxxxxxxX/\"}"
```

### Parâmetros

| Campo | Padrão | Descrição |
|---|---|---|
| `url` | — | Link de qualquer site com mídia (YouTube, Instagram, TikTok, X…) ou o ID de 11 caracteres do YouTube |
| `target_lang` | `PT-BR` | Idioma de destino no formato DeepL (`PT-BR`, `PT-PT`, `EN-US`, …) |
| `translate` | `true` | `false` retorna só a legenda original, sem gastar cota do DeepL |
| `merge_sentences` | `true` | Agrupa linhas em frases antes de traduzir |
| `save` | `true` | Grava o `.txt` em `OUTPUT_DIR` |
| `format` | `json` | `json`, `text` ou `srt` |

Além dos segmentos, a resposta JSON traz `source` (plataforma), `source_url` (link canônico) e
`method` — `legenda` quando veio de faixa publicada, `audio` quando foi ditada pelo Gemini.

### Respostas de erro

- `422` — link inválido, site sem extrator, publicação privada ou apagada, conteúdo que exige
  login (configure `COOKIES_FROM_BROWSER`), vídeo mais longo que `MEDIA_MAX_MINUTES`, ou vídeo sem
  nenhuma fala.
- `502` — falha no tradutor ou na transcrição (chave inválida, cota esgotada, rate limit).

A mensagem em `detail` já diz o que fazer em cada caso.

### Erro 429 / "limitando as requisições deste IP"

O YouTube limita **por IP** o endpoint que serve o texto da legenda, depois de muitas requisições
seguidas. O detalhe que confunde: o resto do YouTube continua funcionando normalmente, então abrir
o vídeo no navegador dá a impressão de que está tudo certo.

Para confirmar qual camada quebrou:

```bash
python -m app.diagnostico https://www.youtube.com/watch?v=SEU_VIDEO
```

Ele testa em separado a página do vídeo, a existência de legendas e o download do texto, e diz
qual das três falhou. Se for o 429: esperar algumas horas, trocar de rede (dados móveis costumam
ter outro IP), ou configurar `YT_PROXY_HTTP` no `.env`.

Na prática o 429 deixou de ser um beco sem saída: o limite é só do endpoint que serve o **texto**
da legenda, e o download da mídia sai por outro caminho. Então o programa cai sozinho na
transcrição por áudio e entrega o texto do mesmo jeito — mais devagar e gastando cota do Gemini,
mas entrega. Para preferir o erro, `AUDIO_FALLBACK=0`.

## Observações

- **Custo:** um vídeo de 1h costuma ter 40–60 mil caracteres. Use `translate=false` para conferir
  a legenda antes de gastar cota. Transcrição por áudio custa bem mais que tradução de texto:
  ~32 tokens por segundo de áudio (e ~8x isso se faltar o `ffmpeg`, porque aí vai vídeo junto).
- **Privacidade:** no plano gratuito do Gemini, o Google pode usar o conteúdo enviado para
  melhorar os modelos. Se a legenda for sensível, use o DeepL ou um plano pago.
- **Bloqueio de IP:** o YouTube bloqueia IPs de datacenter. Rodando local funciona normalmente;
  se você subir isso numa VPS/nuvem e receber erros de "não foi possível obter a legenda",
  configure `YT_PROXY_HTTP`/`YT_PROXY_HTTPS` no `.env` com um proxy residencial.
- **Tempos aproximados:** no caminho do áudio quem marca o início e o fim de cada fala é o
  modelo, não o site. Serve bem para ler e traduzir; para legendar um vídeo com sincronismo
  perfeito, prefira um link que tenha legenda publicada.
- **Vídeo sem fala** (só música ou imagem) falha com mensagem própria — não há o que transcrever.
- **Extratores envelhecem:** site muda, `yt-dlp` quebra. Se um link parar de funcionar do nada,
  `pip install -U yt-dlp` costuma resolver antes de qualquer outra investigação.
