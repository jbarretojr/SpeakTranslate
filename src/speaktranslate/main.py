import argparse

from audio_capture import record_utterance, list_input_devices
from transcription import create_model, transcribe
from translation import translate
from tts import speak

SAMPLE_RATE = 16000


def parse_args():
    parser = argparse.ArgumentParser(
        description='Captura áudio, detecta o idioma, transcreve, traduz e fala o resultado.'
    )
    parser.add_argument('--target-lang', default='pt',
                         help='Código ISO-639-1 do idioma de destino da tradução (padrão: pt)')
    parser.add_argument('--model', default='base',
                         help='Tamanho do modelo faster-whisper (tiny, base, small, medium, large-v3...)')
    parser.add_argument('--device', default='auto', choices=['auto', 'cuda', 'cpu'],
                         help='Dispositivo para rodar o modelo Whisper (padrão: auto)')
    parser.add_argument('--sound-device', type=int, default=None,
                         help='Índice do dispositivo de entrada de áudio (ver --list-devices)')
    parser.add_argument('--silence-duration', type=int, default=900,
                         help='Milissegundos de silêncio para encerrar a gravação (padrão: 900)')
    parser.add_argument('--once', action='store_true',
                         help='Processa uma única gravação e encerra, em vez de rodar em loop')
    parser.add_argument('--list-devices', action='store_true',
                         help='Lista os dispositivos de áudio disponíveis e encerra')
    return parser.parse_args()


def process_once(model, args):
    print('\nFale agora... (aguardando silêncio para encerrar a gravação)')
    audio_data = record_utterance(
        sample_rate=SAMPLE_RATE,
        device=args.sound_device,
        silence_duration_ms=args.silence_duration,
    )
    if audio_data is None:
        print('Nenhuma fala detectada. Tente novamente.')
        return

    print('Transcrevendo...')
    text, detected_lang, probability = transcribe(model, audio_data)
    if not text:
        print('Transcrição vazia. Tente novamente.')
        return

    print(f'[{detected_lang} ({probability:.0%})] {text}')

    translated_text = translate(text, detected_lang, args.target_lang)
    print(f'[{args.target_lang}] {translated_text}')

    print('Sintetizando áudio...')
    speak(translated_text, args.target_lang)


def main():
    args = parse_args()

    if args.list_devices:
        print(list_input_devices())
        return

    print(f'Carregando modelo Whisper "{args.model}"...')
    model = create_model(model_size=args.model, device=args.device)
    print('Modelo carregado.')

    if args.once:
        process_once(model, args)
        return

    print('Pressione Ctrl+C para encerrar.')
    try:
        while True:
            try:
                process_once(model, args)
            except Exception as exc:
                print(f'Erro ao processar a frase: {exc}')
    except KeyboardInterrupt:
        print('\nEncerrando.')


if __name__ == '__main__':
    main()
