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

```bash
poetry run python run.py
```

A aplicação roda em loop: grava até detectar uma pausa na fala, transcreve, detecta o idioma, traduz e fala o resultado. Pressione `Ctrl+C` para encerrar.

### Opções

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
