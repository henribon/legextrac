# legextrac

API em Python que recebe um link do YouTube, extrai a legenda/transcrição do vídeo e traduz para
português usando o DeepL.

## Como funciona

1. `POST /transcript` recebe a URL do vídeo.
2. `youtube-transcript-api` busca **sempre a legenda original**, no idioma falado no vídeo.
3. As linhas são agrupadas em frases — legendas quebram frases no meio, e traduzir fragmentos
   isolados piora bastante o resultado.
4. As frases vão em lotes para o tradutor — **Gemini** por padrão, DeepL como alternativa.
5. Grava um `.txt` com a tradução na pasta `output/` (configurável em `OUTPUT_DIR`).
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
Idioma original: English (en)
Traduzido para: PT-BR
Gerado em: 11/08/2026 09:28
------------------------------------------------------------

Isto é um 3.
Está escrito de forma desleixada, mas seu cérebro lê sem dificuldade.
```

Detalhes:

- O título vem do oEmbed público do YouTube. Se essa chamada falhar, o arquivo fica só com o ID —
  não é motivo para a requisição inteira falhar.
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
| `%LOCALAPPDATA%\Programs\legextrac\legextrac.exe` | o app, ~15 MB, sem depender do projeto |
| `%APPDATA%\legextrac\.env` | a chave da API, fora do executável |
| Menu Iniciar `legextrac.lnk` | o atalho, com ícone |

Depois disso a pasta do projeto pode ser movida ou apagada — o app continua funcionando. Se o
`.exe` ainda não tiver sido compilado, o `instalar.py` cria o atalho apontando para o Python do
projeto, que funciona igual mas depende da pasta.

**A chave fica fora do `.exe`**, em `%APPDATA%\legextrac\.env`. Isso é de propósito: o executável
pode ser copiado para outra máquina sem levar segredo junto — lá, basta criar o `.env` na mesma
pasta de configuração. A busca é em ordem: pasta atual, pasta do executável, `%APPDATA%\legextrac`.
Variável de ambiente do sistema tem prioridade sobre todas.

A janela tem um campo para o link e o botão **TRANSCREVER**. Ao terminar, o arquivo é salvo na
pasta **Downloads** e o Explorer abre com ele já selecionado.

Detalhes:

- Se você copiou o link antes de abrir o app, o campo já vem preenchido.
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

### Parâmetros

| Campo | Padrão | Descrição |
|---|---|---|
| `url` | — | Link `watch`, `youtu.be`, `shorts`, `embed`, `live` ou o ID de 11 caracteres |
| `target_lang` | `PT-BR` | Idioma de destino no formato DeepL (`PT-BR`, `PT-PT`, `EN-US`, …) |
| `translate` | `true` | `false` retorna só a legenda original, sem gastar cota do DeepL |
| `merge_sentences` | `true` | Agrupa linhas em frases antes de traduzir |
| `save` | `true` | Grava o `.txt` em `OUTPUT_DIR` |
| `format` | `json` | `json`, `text` ou `srt` |

### Respostas de erro

- `422` — link inválido, vídeo sem legenda, legendas desativadas, vídeo privado, restrição de
  idade, ou **IP bloqueado pelo YouTube**.
- `502` — falha no tradutor (chave inválida, cota esgotada, rate limit).

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
ter outro IP), ou configurar `YT_PROXY_HTTP` no `.env`. Trocar de biblioteca não resolve — o
`yt-dlp` bate no mesmo endpoint e toma o mesmo 429.

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
