# 🔮 Silva

**Silva** é um companheiro virtual de desktop com IA: um gato-mago em pixel art que acompanha
o usuário no Windows, vê a tela sob demanda, ouve e fala, lembra de coisas, comenta sozinho de
vez em quando (inclusive notícias reais), e tem controle real e permissionado sobre o sistema
(abrir/fechar apps, ajustar volume por aplicativo, pesquisar na web).

---

## 🌟 O que já está pronto

### Personagem & Janela
- **Poses estáticas por contexto** (dormindo, jogando, bravo, feliz, lendo, pensando, etc.) — o
  `SpriteLoader` detecta e recorta automaticamente a maior região conectada de pixels de cada
  imagem (`cv2.connectedComponentsWithStats`), então funciona mesmo com sprites com
  artefatos/vazamento de arte vizinha.
- Janela **transparente, sempre no topo**, com **Modo Click-Through** opcional (não bloqueia
  cliques nos apps atrás dela).
- **Posição inicial ancorada de verdade no canto inferior direito**, calculada pela geometria
  real da tela (funciona em qualquer resolução/escala de DPI, não é um pixel fixo).

### IA & Conversa
- **Roteamento por complexidade**: perguntas simples/comandos usam um modelo rápido
  (`meta/llama-3.1-8b-instruct`, ~3s de resposta); perguntas que parecem precisar de raciocínio
  real (explicações, comparações, "por quê"/"como funciona", mensagens longas) roteiam
  automaticamente pra um modelo mais forte (`meta/llama-3.1-70b-instruct`, mais lento porém bem
  mais coerente). Visão sempre usa um terceiro modelo dedicado com suporte a imagem.
- **Fala espontânea** ("como numa chamada"): comenta sozinho de vez em quando quando o usuário
  fica quieto — piadas, curiosidades, perguntas sobre o dia, ou **notícias reais** (ver abaixo).
  Liga/desliga a qualquer momento por voz ou texto: "pare de falar aleatoriamente" /
  "ativar falar aleatoriamente".
- **Notícias reais** (Brasil + mundo), via RSS público do Google Notícias — sem API key. A
  manchete mais em destaque de cada feed é sinalizada como prioridade; cada manchete é oferecida
  no máximo 2 vezes antes de sair de rotação, pra não ficar repetindo o mesmo assunto.
- **Memória de conversa correta**: tudo que a Silva fala — inclusive comentários espontâneos —
  entra no histórico, então perguntar "me conta mais sobre isso" depois funciona de verdade.
- **Memória de longo prazo**: banco SQLite local ("Guarde isso", "Esqueça isso").
- **Modo Nerd**: postura mais proativa (fala espontânea mais frequente), liga/desliga a qualquer
  momento por voz ou texto — "vira nerd" / "ativa o modo nerd" / "desliga o modo nerd". Resposta
  de confirmação é instantânea e determinística (não passa pela IA), e o personagem assume uma
  pose visual diferente enquanto ativo.
- **Pesquisa real em segundo plano** ("pesquisa X"): busca de verdade na web (DuckDuckGo, sem API
  key) + resumo pela IA baseado só nos resultados reais (nunca inventa — se não achar nada, diz
  isso claramente). Não trava a conversa: responde na hora ("pode deixar, já te aviso") e, quando
  a busca termina, a Silva anuncia o resultado sozinha, na própria voz.

### Visão de Tela
- Captura sob demanda (nunca grava nada em disco) e envia como imagem só quando a mensagem
  realmente parece ser sobre a tela (palavras como "tela", "isso aqui", "traduz", ou o comando
  "minha tela") — não em toda mensagem.
- Monitoramento periódico de contexto usa só **diff matemático de pixels** (`mss`), sem enviar
  imagem nenhuma, exceto quando explicitamente solicitado.
- **Tradução sob demanda** ("Traduz isso"): OCR via Tesseract. Requer o
  [Tesseract-OCR](https://github.com/UB-Mannheim/tesseract) instalado no sistema
  (`winget install --id UB-Mannheim.TesseractOCR -e`) — binário externo, não é dependência Python.

### Voz
- **Push-to-Talk (F8)** e **modo mãos-livres** (tecla `+`) via microfone, transcrito **localmente**
  com `faster-whisper` (modelo `small` por padrão, configurável) — nunca sai pra nuvem.
- **Ouve o áudio do próprio PC/jogo** (loopback WASAPI) — ativa por voz ("está ouvindo o som do
  jogo/pc") ou pela tecla `Ctrl+-`, também transcrito localmente.
- TTS via EdgeTTS (voz masculina, tom ajustável) ou pyttsx3, configurável em Configurações → Voz.

### Ações no Sistema (Tool Registry + permissões em camadas)
Toda ação passa por um `ToolRegistry` central com tier de permissão (`SAFE` / `CONFIRM` /
`DANGEROUS`) — não é mais um if/elif solto. Hoje:
- **Abrir e fechar aplicativos** da `allowlist` do `config.json` (`open_application` /
  `close_application`) — fechar casa o nome configurado com o processo real rodando (ex:
  "vscode" ↔ `Code.exe`).
- **Abrir URL** / **pesquisar na web**.
- **Ajustar volume por aplicativo** no mixer de som do Windows ("abaixa o som do discord", "muta
  o chrome") — via `pycaw`, funciona com qualquer app tocando som no momento, não só os da
  allowlist (é reversível e não abre/fecha nada, então não precisa de allowlist pra isso).
- **Guardar/esquecer memória**.

`CONFIRM` hoje executa e sinaliza num evento próprio (ainda não existe um diálogo de confirmação
de verdade — ver Roadmap). `DANGEROUS` existe como tier reservado; nenhuma ação usa ainda, e
qualquer coisa marcada assim seria recusada por padrão (fail-safe) até esse tier ganhar uso real.

### Sistema & Conveniência
- **Inicialização automática com o Windows**, ativa por padrão — liga/desliga a qualquer momento
  em Configurações → Geral, sem precisar reinstalar nada. Usa a chave do usuário no registro
  (`HKCU\...\Run`), sem precisar de admin.

---

## 🚀 Instalação no Windows

1. Certifique-se de ter o **Python 3.11+** instalado e adicionado ao `PATH`.
2. Dê um duplo clique no arquivo `install.bat` para criar o ambiente virtual e instalar todas as
   dependências.

## 🎮 Execução

Dê um duplo clique no arquivo `run.bat` (ou deixe a inicialização automática cuidar disso).

Na primeira execução, o **Setup Wizard** guia a escolha do nome da personagem, chave de API,
voz e permissões iniciais.

---

## ⌨️ Atalhos e Comandos

| Atalho / Frase | Efeito |
|---|---|
| **F8** (segurar) | Push-to-Talk — grava enquanto segura, transcreve ao soltar |
| **`+`** | Liga/desliga o modo mãos-livres de voz (escuta contínua, sem precisar segurar F8) |
| **`-`** | Liga/desliga a Visão de Tela permanentemente |
| **`Ctrl+-`** | Liga/desliga escutar o áudio do jogo/PC |
| **"minha tela"** (voz/texto) | Ativa a Visão de Tela na hora |
| **"está ouvindo o som do jogo/pc"** | Ativa escutar o áudio do sistema |
| **"pare"/"ativar falar aleatoriamente"** | Liga/desliga a fala espontânea |
| **"vira nerd"/"desliga o modo nerd"** | Liga/desliga o Modo Nerd (mais proativo) |
| **"pesquisa [assunto]"** | Dispara pesquisa real em segundo plano, avisa quando terminar |
| Duplo clique na Silva | Abre a janela de Chat |
| Botão direito / bandeja | Menu de contexto (visão, configurações, sair) |

> ⚠️ `+`, `-` e `Ctrl+-` são atalhos **globais** (via `keyboard`) — funcionam mesmo com outro app
> em foco, então digitar esses caracteres em qualquer programa também aciona o atalho. Se
> atrapalhar, desative o app ou ajuste as teclas em `src/core/app.py`.

---

## 🔒 Privacidade e Segurança

- Visão de tela **OFF por padrão**; captura só é enviada quando a mensagem parece ser sobre a
  tela, nunca em toda mensagem — e nunca é gravada em disco.
- Áudio (microfone e som do sistema) é transcrito **localmente**, nunca enviado a um servidor de
  terceiros além do provedor de IA escolhido para o texto da conversa em si.
- Nenhum comando de shell arbitrário é executado — só as ações estruturadas do Tool Registry,
  cada uma com seu tier de permissão, e abrir/fechar app é restrito à `allowlist` do
  `config.json`.
- Segredos (API key) ficam em `.env`, nunca no `config.json` versionado.

---

## 🧪 Testes

```
pytest tests/ --cov=src --cov-report=term-missing
```

365 testes cobrindo orquestrador, ferramentas/permissões, voz, visão, memória, notícias,
mixer de som, autostart, pesquisa em segundo plano, Modo Nerd, sprites/animação e configuração.

---

## 🗺️ Roadmap — o que falta

Silva está evoluindo de "conjunto de features" pra uma arquitetura de **Local AI Desktop Agent**
(Agent Core, Tool Registry já feito acima). O que falta, em ordem:

- **Visão contínua de verdade**: hoje é liga/desliga por palavra-chave. Falta um buffer circular
  com TTL, modos explícitos (OFF/CONTEXT/AWARENESS/ACTIVE), e diferenciação entre contexto
  atual/recente/expirado — sem nunca mandar pro modelo uma leitura de tela velha como se fosse
  atual.
- **Memória em camadas**: hoje é só key/value + histórico plano. Falta separar working/short-term/
  long-term, filtrar relevância antes de montar o prompt (hoje tudo entra sempre), e preparar
  espaço pra RAG local (documentos/código) sem dependência pesada obrigatória.
- **Persona/Emotion Engine separados**: personalidade hoje vive inteira dentro do prompt de
  sistema; emoção e estado funcional (pensando/falando) ainda dividem o mesmo campo de animação.
- **Scheduler**: nenhum conceito de lembrete/timer/tarefa recorrente existe ainda
  ("me lembra em 30 minutos", "às 18h me avisa").
- **Confirmação real pro tier CONFIRM**: hoje ações CONFIRM (abrir/fechar app, ajustar volume)
  executam e só sinalizam num evento — falta um diálogo de "permitir uma vez / sempre / negar".
- **Testes de segurança dedicados**: bypass de permissão, parâmetros inválidos, path traversal —
  hoje a cobertura de segurança é indireta via testes de allowlist/tiers.
- **Documentação e CI**: sem `docs/` detalhado (arquitetura, segurança, cada subsistema) nem
  GitHub Actions (lint/testes automáticos a cada push).
- **Plugins**: nenhuma estrutura de plugin existe ainda — planejado como interface simples
  (`plugins/discord/`, `plugins/spotify/`, etc.), não uma prioridade imediata.
- **Empacotamento**: hoje roda só via `install.bat`/`run.bat` + Python — gerar um instalador
  (`Silva-Setup.exe`) fica pra depois, sem prioridade sobre o resto.
