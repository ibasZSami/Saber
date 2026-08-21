# Empacotamento — gerando o Silva-Setup.exe

Hoje o Silva roda direto do código-fonte (`install.bat` + `run.bat`). Este
diretório gera um instalador Windows de verdade a partir desse mesmo código,
em duas etapas: **PyInstaller** empacota o app Python num executável
standalone; **Inno Setup** transforma esse executável num instalador com
atalho, desinstalador e tudo mais.

## 1. Empacotar com PyInstaller

Dentro do venv do projeto (o mesmo criado por `install.bat`):

```
pip install pyinstaller
pyinstaller packaging/silva.spec --noconfirm
```

Isso gera `dist/Silva/Silva.exe` — uma pasta "onedir" com o executável e
tudo que ele precisa ao lado (não onefile: onedir inicia mais rápido e deixa
`config.json`/`data/` viverem direto ao lado do `.exe`, em vez de um diretório
temporário recriado a cada execução).

O `.spec` já inclui `extracted_assets/silva/` (sprites do personagem) e
`plugins/` (exemplos, editáveis pelo usuário) na pasta gerada — sem eles o
app sobe sem visual e sem plugins.

`config.json` e `data/` **não** são empacotados de propósito: o app já cria
os dois sozinhos na primeira execução (`Settings.load()` chama `.save()`
quando o arquivo não existe), então cada instalação começa com config limpo
em vez de herdar o `config.json` do computador onde foi gerado o build
(que tem caminhos absolutos daquela máquina).

## 2. Gerar o instalador com Inno Setup

Requer o [Inno Setup](https://jrsoftware.org/isinfo.php) instalado (download
único, gratuito — não é uma dependência Python, por isso não entra no
`requirements.txt`).

```
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\silva.iss
```

Gera `dist/Silva-Setup.exe`: instala em `%LOCALAPPDATA%\Programs\Silva` (não
pede admin — `PrivilegesRequired=lowest`), cria atalho no Menu Iniciar e,
opcionalmente, na Área de Trabalho, registra desinstalador em
"Aplicativos e recursos", e oferece rodar a Silva ao final da instalação.

O autostart ("iniciar com o Windows") **não** é uma opção do instalador —
a própria Silva já gerencia isso pela tela de Configurações
(`src/core/autostart.py`, Scheduled Task com fallback pra chave de registro).
Um segundo mecanismo no instalador so duplicaria o registro.

**Aviso do Windows ao abrir pela primeira vez**: como `Silva.exe`/
`Silva-Setup.exe` não são assinados digitalmente (certificado de assinatura
de código é pago, fora de escopo aqui), o SmartScreen do Windows normalmente
mostra "O Windows protegeu o computador" no primeiro uso — clicar em "Mais
informações" → "Executar assim mesmo" resolve, comportamento padrão pra
qualquer executável indie não assinado. Numa máquina com uma política de
Controle de Aplicativo (WDAC) mais restritiva — o caso deste ambiente de
build, onde `Silva.exe` recém-gerado foi bloqueado até por `cmd /c start`,
impedindo um smoke test real de boot aqui — a execução pode ficar bloqueada
de vez, sem contornar via linha de comando; nesse cenário o bloqueio é uma
política do próprio Windows/administrador da máquina, não um problema do
`.exe` em si.

## O que continua fora do instalador

Estas duas dependências continuam externas, exatamente como hoje via
`install.bat` — não são pacotes pip, e empacotá-las junto infla o instalador
em centenas de MB para uma minoria dos usuários que usa cada recurso:

- **Tesseract-OCR** (tradução de tela): `winget install --id UB-Mannheim.TesseractOCR -e`
- **Chromium do Playwright** (automação real de navegador): requer Python
  para rodar `python -m playwright install chromium` — quem instalou via
  `Silva-Setup.exe` (sem Python) e quer essa função ativa precisa instalar
  o Chromium manualmente ou usar a instalação via código-fonte.

O instalador mostra esses dois avisos na tela final (ver `[Run]`/mensagens
em `silva.iss`) — funcionalidades que dependem deles simplesmente ficam
indisponíveis (mesmo comportamento de "capacidade nunca oferecida" que o
resto do app já usa quando uma dependência opcional falta).

## Versionamento

`#define MyAppVersion` no topo de `silva.iss` — bump manual a cada release,
não há automação de versão neste momento.
