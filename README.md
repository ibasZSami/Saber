# 🔮 Shimeji AI Companion (Lumi)

**Shimeji AI Companion (Lumi)** é uma evolução do conceito tradicional de Shimeji para um verdadeiro **companheiro virtual de desktop com IA**, visão de tela inteligente, voz, memória local, animações em pixel art e capacidade controlada de interagir com o sistema operacional.

---

## 🌟 Recursos Principais

- **Personagem Pixel Art Dark Fantasy (Lumi)**: 44 faixas de animação transparente recortadas e fatiadas automaticamente.
- **Janela Transparente & Always-on-Top**: Redimensionável, arrastável por clique com suporte a **Modo Click-Through** (não bloqueia cliques em aplicativos de fundo).
- **Visão de Tela Inteligente**: Captura rápida com `mss` e detecção matemática de alterações para evitar chamadas de API desnecessárias.
- **Tradução Sob Demanda ("Traduz isso")**: Extrai o texto da tela via OCR e traduz apenas quando solicitado explicitamente pelo usuário.
- **Reconhecimento de Voz & TTS**: Entrada por atalho Push-to-Talk (F8) e síntese de voz fluida via EdgeTTS/pyttsx3.
- **Interação Desktop com Permissões**: Executa abertura de softwares e pesquisas na web via `allowlist.json` de segurança.
- **Memória de Curto e Longo Prazo**: Banco SQLite local armazenando preferências ("Guarde isso", "Esqueça isso").

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

- **F8 (Push-to-Talk)**: Pressione para falar com a Lumi via microfone.
- **Duplo Clique na Lumi**: Abre a janela de Chat.
- **Botão Direito na Lumi ou Ícone da Bandeja (System Tray)**: Menu de contexto para visão, atalhos e configurações.

---

## 🔒 Privacidade e Segurança

- A visão da tela permanece **OFF por padrão** ou operando em **Modo Privado**.
- Nenhuma screenshot é enviada continuamente sem detecção prévia de alterações de cena.
- NENHUM comando shell arbitrário é executado no sistema operacional.
