# SpeakTranslate

Captura o áudio do microfone, detecta o idioma falado, transcreve, traduz para o idioma de destino (português por padrão) e reproduz o resultado em áudio.

Pipeline: **captura de áudio** → **detecção de idioma + transcrição** ([faster-whisper](https://github.com/SYSTRAN/faster-whisper)) → **tradução** ([deep-translator](https://github.com/nidhaloff/deep-translator)/Google) → **texto-para-voz** ([edge-tts](https://github.com/rany2/edge-tts)).

O diretório [`example/`](example) contém o projeto de referência (VoiceNote), que fornece apenas a parte de captura + transcrição via faster-whisper.

## Pré-requisitos

- Python `3.11` ou mais recente
- [Poetry](https://python-poetry.org/docs/#installation)
- Conexão com a internet (tradução via Google e síntese de voz via edge-tts são serviços online)

## Instalação

```bash
poetry install
```

## Uso

### Interface gráfica (tkinter)

```bash
poetry run python run_gui.py
```

Escolha o idioma de destino, o modelo Whisper e o dispositivo de entrada de áudio (use **Atualizar** se conectar/desconectar um dispositivo). O botão funciona como o atalho `Ctrl+Shift+Space` do VoiceNote (em [`example/`](example)): clique uma vez em **🎙 Iniciar Gravação** para começar a gravar, e clique novamente em **⏹ Parar Gravação** para encerrar a captura — a partir daí a transcrição, tradução e fala rodam sozinhas até o fim (o botão fica em "Processando..." nesse meio-tempo) e o app volta a ficar pronto para uma nova gravação. O log de transcrições e traduções aparece na janela.

Por padrão, a lista de "Entrada de áudio" mostra os microfones disponíveis no sistema. Para transcrever o que está tocando no computador (ex.: áudio de um navegador ou outro app) em vez do microfone, é necessário instalar um driver de áudio virtual com loopback, como o [BlackHole](https://github.com/ExistentialAudio/BlackHole) (gratuito), e configurar um "Dispositivo de Múltiplas Saídas" (Multi-Output Device) no Configurador de Áudio e MIDI do macOS para que o som saia tanto pelos alto-falantes quanto pelo BlackHole. Depois disso, o BlackHole aparece como uma opção de entrada nesta lista.

### Linha de comando

```bash
poetry run python run.py
```

A aplicação roda em loop: grava até detectar uma pausa na fala, transcreve, detecta o idioma, traduz e fala o resultado. Pressione `Ctrl+C` para encerrar.

### Opções (CLI)

```bash
poetry run python run.py --target-lang pt        # idioma de destino (padrão: pt)
poetry run python run.py --model small            # tamanho do modelo Whisper
poetry run python run.py --device cpu             # cpu | cuda | auto
poetry run python run.py --once                   # processa uma única gravação e encerra
poetry run python run.py --list-devices           # lista dispositivos de áudio disponíveis
poetry run python run.py --sound-device 2         # índice do dispositivo de entrada
```

## Licença

Este projeto está licenciado sob a Licença Pública Geral GNU. Consulte o arquivo [LICENSE](LICENSE) para mais detalhes.
