# 🔮 Shimeji AI Companion (Silva)

**Shimeji AI Companion (Silva)** é uma evolução do conceito tradicional de Shimeji para um verdadeiro **companheiro virtual de desktop com IA**, visão de tela inteligente, voz, memória local, animações em pixel art e capacidade controlada de interagir com o sistema operacional.

---

## 🌟 Recursos Principais

- **Personagem Pixel Art (Silva, o gato-mago)**: poses estáticas por contexto (dormindo, jogando, bravo, feliz, lendo, etc.) — o `SpriteLoader` detecta e recorta automaticamente a maior região conectada de pixels de cada imagem, então funciona mesmo com sprites que têm artefatos/vazamento de arte vizinha.
- **Janela Transparente & Always-on-Top**: Redimensionável, arrastável por clique com suporte a **Modo Click-Through** (não bloqueia cliques em aplicativos de fundo).
- **Visão de Tela Real**: Quando ativada (e fora do Modo Privado), captura a tela e envia como imagem para modelos de IA com suporte a visão (ex: `meta/llama-3.2-90b-vision-instruct` na NVIDIA, `gpt-4o` na OpenAI). Também usa detecção matemática de alterações (`mss` + diff) para o monitoramento periódico de contexto.
- **Tradução Sob Demanda ("Traduz isso")**: Extrai o texto da tela via OCR (Tesseract) e traduz apenas quando solicitado explicitamente pelo usuário. **Requer o [Tesseract-OCR](https://github.com/UB-Mannheim/tesseract) instalado no sistema** (`winget install --id UB-Mannheim.TesseractOCR -e`), já que é um binário externo, não uma dependência Python.
- **Reconhecimento de Voz & TTS**: Push-to-Talk real via atalho global **F8** — grava o microfone e transcreve localmente com `faster-whisper` (modelo `small` por padrão, configurável, baixado na primeira execução), sem depender de nuvem. Síntese de voz via EdgeTTS/pyttsx3. Requer `"microphone_enabled": true` no config.
- **Interação Desktop com Permissões**: Executa abertura de softwares e pesquisas na web via `allowlist` no `config.json`.
- **Memória de Curto e Longo Prazo**: Banco SQLite local armazenando preferências ("Guarde isso", "Esqueça isso") — a IA aciona isso via ações estruturadas no JSON de resposta.

---

## 🚀 Instalação no Windows

1. Certifique-se de ter o **Python 3.11+** instalado e adicionado ao `PATH`.
2. Dê um duplo clique no arquivo `install.bat` para criar o ambiente virtual e instalar todas as dependências.

---

## 🎮 Execução

Dê um duplo clique no arquivo `run.bat`.

Ao executar pela primeira vez, o **Setup Wizard** guiará você na escolha do nome da personagem, chave da API da OpenAI/Ollama, voz e permissões iniciais.

---

## ⌨️ Atalhos e Comandos

- **F8 (Push-to-Talk)**: Segure para falar com a Silva via microfone e solte quando terminar. Requer `"microphone_enabled": true`.
- **Tecla `+`**: Liga/desliga o **modo mãos-livres** de voz — com ele ativo, não precisa segurar F8: a Silva escuta continuamente e transcreve cada fala automaticamente (detecção simples de silêncio), até você apertar `+` de novo pra desligar.
- **Tecla `-`**: Liga/desliga a **Visão de Tela** permanentemente (equivalente a ativar Visão de Tela + desligar Modo Privado nas Configurações).
- **Comando de voz/texto "minha tela"**: ativa a Visão de Tela na hora, sem precisar mexer nas Configurações ou apertar `-`.
- **Duplo Clique na Silva**: Abre a janela de Chat.
- **Botão Direito na Silva ou Ícone da Bandeja (System Tray)**: Menu de contexto para visão, atalhos e configurações.

> ⚠️ `+` e `-` são atalhos **globais** (funcionam mesmo com outro app em foco) via a lib `keyboard`. Isso significa que apertar esses caracteres em qualquer outro programa enquanto o Silva está rodando também aciona o atalho — se isso atrapalhar (ex: digitando um e-mail com "-"), desative o app ou ajuste as teclas em `src/core/app.py`.

---

## 🔒 Privacidade e Segurança

- A visão da tela permanece **OFF por padrão** ou operando em **Modo Privado**.
- Com a Visão de Tela ativada e o Modo Privado desligado, uma captura da tela só é enviada quando a mensagem parece ser sobre a tela (palavras como "tela", "isso aqui", "traduz", ou o comando "minha tela") — não em toda mensagem, pra não deixar a conversa lenta à toa.
- O monitoramento periódico de contexto (detecção de app/jogo) usa apenas diffs matemáticos de pixel, sem enviar imagens, exceto quando explicitamente solicitado.
- O áudio do microfone (Push-to-Talk e modo mãos-livres) é transcrito **localmente** via `faster-whisper` — nunca é enviado a um servidor externo.
- NENHUM comando shell arbitrário é executado no sistema operacional — apenas aplicativos pré-cadastrados na allowlist.
