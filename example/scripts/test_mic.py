#!/usr/bin/env python3
"""
Diagnóstico de captura de áudio e transcrição do VoiceNote.

Uso:
    poetry run python scripts/test_mic.py
    poetry run python scripts/test_mic.py --device 0
    poetry run python scripts/test_mic.py --full
"""

import argparse
import os
import sys
import time
import wave
from collections import deque

import numpy as np
import sounddevice as sd
import webrtcvad
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
sys.path.insert(0, SRC)

from utils import resolve_record_sample_rate, resample_audio, VAD_SAMPLE_RATES

CONFIG_PATH = os.path.join(SRC, 'config.yaml')
OUTPUT_DIR = os.path.join(ROOT, 'scripts', 'test_output')


def load_config():
    defaults = {
        'sample_rate': 16000,
        'silence_duration': 900,
        'min_duration': 100,
        'recording_mode': 'continuous',
        'sound_device': None,
        'language': 'pt',
    }
    if not os.path.isfile(CONFIG_PATH):
        return defaults

    with open(CONFIG_PATH, 'r') as f:
        config = yaml.safe_load(f) or {}

    recording = config.get('recording_options', {})
    model = config.get('model_options', {})
    return {
        **defaults,
        'sample_rate': recording.get('sample_rate') or defaults['sample_rate'],
        'silence_duration': recording.get('silence_duration') or defaults['silence_duration'],
        'min_duration': recording.get('min_duration') or defaults['min_duration'],
        'recording_mode': recording.get('recording_mode') or defaults['recording_mode'],
        'sound_device': recording.get('sound_device'),
        'language': model.get('common', {}).get('language') or defaults['language'],
        'use_api': model.get('use_api', False),
        'local_model': model.get('local', {}).get('model', 'base'),
        'device': model.get('local', {}).get('device', 'auto'),
    }


def print_devices():
    print('\n=== Dispositivos de áudio ===')
    print(sd.query_devices())
    default_in, default_out = sd.default.device
    print(f'\nEntrada padrão: {default_in}')
    print(f'Saída padrão:   {default_out}')
    print('\nDispositivos com entrada (microfone):')
    for i, dev in enumerate(sd.query_devices()):
        if dev['max_input_channels'] > 0:
            marker = ' *' if i == default_in else ''
            supported = [str(r) for r in VAD_SAMPLE_RATES if _supports_rate(i, r)]
            rates = ', '.join(supported) if supported else 'requer fallback (ex: 48000 Hz)'
            print(f"  [{i}] {dev['name']} ({dev['max_input_channels']} in){marker}")
            print(f"       taxas VAD/Voice OK: {rates} Hz")


def _supports_rate(device, sample_rate):
    try:
        sd.check_input_settings(device=device, samplerate=sample_rate, channels=1, dtype='int16')
        return True
    except Exception:
        return False


def prepare_recording(device, target_rate):
    record_rate = resolve_record_sample_rate(device, target_rate)
    if record_rate != target_rate:
        print(f'  Dispositivo não suporta {target_rate} Hz — gravando a {record_rate} Hz e convertendo depois.')
    return record_rate


def save_wav(path, audio_data, sample_rate):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data.tobytes())


def analyze_audio(audio_data, sample_rate):
    if audio_data.size == 0:
        return {'duration': 0, 'peak': 0, 'rms': 0, 'silent': True}

    peak = int(np.max(np.abs(audio_data)))
    rms = float(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)))
    duration = len(audio_data) / sample_rate
    return {
        'duration': duration,
        'peak': peak,
        'rms': rms,
        'silent': peak < 100,
    }


def record_simple(device, target_rate, seconds):
    record_rate = prepare_recording(device, target_rate)
    print(f'\nGravando {seconds}s no dispositivo {device!r}...')
    print('Fale algo agora!')
    audio = sd.rec(
        int(seconds * record_rate),
        samplerate=record_rate,
        channels=1,
        dtype='int16',
        device=device,
    )
    sd.wait()
    audio = audio.flatten()
    return resample_audio(audio, record_rate, target_rate), target_rate


def record_like_app(device, target_rate, silence_duration_ms, recording_mode, max_seconds=30):
    """Replica a lógica de gravação do ResultThread."""
    record_rate = prepare_recording(device, target_rate)
    frame_duration_ms = 30
    frame_size = int(record_rate * (frame_duration_ms / 1000.0))
    silence_frames = int(silence_duration_ms / frame_duration_ms)
    initial_frames_to_skip = int(0.15 * record_rate / frame_size)

    use_vad = recording_mode in ('voice_activity_detection', 'continuous')
    vad = webrtcvad.Vad(2) if use_vad else None
    speech_detected = False
    silent_frame_count = 0

    audio_buffer = deque(maxlen=frame_size)
    recording = []
    from threading import Event
    data_ready = Event()

    def callback(indata, frames, time_info, status):
        if status:
            print(f'  [aviso stream] {status}')
        audio_buffer.extend(indata[:, 0])
        data_ready.set()

    print(f'\nGravando como o app (modo: {recording_mode}, VAD: {use_vad})...')
    print('Fale algo e depois fique em silêncio por ~1 segundo.')
    if not use_vad:
        print(f'Gravação fixa de {max_seconds}s (modo sem VAD).')

    start = time.time()
    with sd.InputStream(
        samplerate=record_rate,
        channels=1,
        dtype='int16',
        blocksize=frame_size,
        device=device,
        callback=callback,
    ):
        while True:
            if time.time() - start > max_seconds:
                print('  Tempo máximo atingido, encerrando gravação.')
                break

            data_ready.wait(timeout=1.0)
            data_ready.clear()

            if len(audio_buffer) < frame_size:
                continue

            frame = np.array(list(audio_buffer), dtype=np.int16)
            audio_buffer.clear()
            recording.extend(frame)

            if initial_frames_to_skip > 0:
                initial_frames_to_skip -= 1
                continue

            if vad:
                if vad.is_speech(frame.tobytes(), record_rate):
                    silent_frame_count = 0
                    if not speech_detected:
                        print('  Fala detectada pelo VAD.')
                        speech_detected = True
                else:
                    silent_frame_count += 1

                if speech_detected and silent_frame_count > silence_frames:
                    print('  Silêncio detectado, encerrando gravação.')
                    break
            elif len(recording) >= record_rate * max_seconds:
                break

    audio = np.array(recording, dtype=np.int16)
    if record_rate != target_rate:
        audio = resample_audio(audio, record_rate, target_rate)
    return audio, speech_detected


def test_transcription(audio_data, sample_rate, config):
    from utils import ConfigManager
    from transcription import create_local_model, transcribe

    ConfigManager.initialize()
    print('\nCarregando modelo local (pode demorar)...')
    model = create_local_model()
    print('Transcrevendo...')
    result, _ = transcribe(audio_data, model)
    print(f'\nResultado: {result!r}')
    return result


def print_diagnosis(stats, speech_detected, min_duration_ms, recording_mode):
    print('\n=== Diagnóstico ===')
    print(f"  Duração:  {stats['duration']:.2f}s")
    print(f"  Pico:     {stats['peak']} (ideal: > 1000)")
    print(f"  RMS:      {stats['rms']:.0f} (ideal: > 200)")
    print(f"  VAD viu fala: {'sim' if speech_detected else 'não'}")

    issues = []
    if stats['silent']:
        issues.append('Áudio quase silencioso — microfone errado, mudo ou volume muito baixo.')
    if stats['duration'] * 1000 < min_duration_ms:
        issues.append(f'Gravação menor que min_duration ({min_duration_ms}ms) — seria descartada pelo app.')
    if recording_mode in ('continuous', 'voice_activity_detection') and not speech_detected:
        issues.append('VAD não detectou fala — o app ficaria gravando até você pressionar o atalho de novo.')
    if stats['peak'] > 0 and stats['peak'] < 500:
        issues.append('Sinal fraco — aproxime o microfone ou aumente o ganho no sistema.')

    if issues:
        print('\nProblemas encontrados:')
        for i, issue in enumerate(issues, 1):
            print(f'  {i}. {issue}')
    else:
        print('\nCaptura parece OK. Se o app não transcreve, verifique:')
        print('  - Se clicou em Iniciar antes de usar o atalho')
        print('  - Se o atalho ctrl+shift+space está sendo reconhecido (permissões de teclado)')
        print('  - Se há texto no terminal ao falar (print_to_terminal)')


def main():
    parser = argparse.ArgumentParser(description='Teste de microfone do VoiceNote')
    parser.add_argument('--device', type=int, default=None, help='Índice do dispositivo de entrada')
    parser.add_argument('--seconds', type=int, default=3, help='Segundos para teste simples')
    parser.add_argument('--full', action='store_true', help='Incluir teste de transcrição')
    parser.add_argument('--list-only', action='store_true', help='Só listar dispositivos')
    args = parser.parse_args()

    config = load_config()
    print('=== VoiceNote — teste de microfone ===')
    print(f'Configuração: {CONFIG_PATH}')
    print(f"  sample_rate:      {config['sample_rate']}")
    print(f"  sound_device:     {config['sound_device']}")
    print(f"  recording_mode:   {config['recording_mode']}")
    print(f"  silence_duration: {config['silence_duration']}ms")
    print(f"  language:         {config['language']}")

    print_devices()
    if args.list_only:
        return

    device = args.device if args.device is not None else config['sound_device']
    print(f'\nDispositivo usado no teste: {device!r} (null = padrão do sistema)')

    try:
        prepare_recording(device, config['sample_rate'])
    except ValueError as e:
        print(f'\nERRO: {e}')
        print('Recomendado no Linux: poetry run python scripts/test_mic.py --device 16')
        return

    # Teste 1: gravação simples
    print('\n--- Teste 1: gravação simples ---')
    try:
        simple, target_rate = record_simple(device, config['sample_rate'], args.seconds)
        stats = analyze_audio(simple, target_rate)
        path = os.path.join(OUTPUT_DIR, 'test_simple.wav')
        save_wav(path, simple, target_rate)
        print(f'Arquivo salvo: {path}')
        print(f"  Duração: {stats['duration']:.2f}s | Pico: {stats['peak']} | RMS: {stats['rms']:.0f}")
    except Exception as e:
        print(f'ERRO no teste simples: {e}')
        print('Tente o dispositivo padrão: poetry run python scripts/test_mic.py --device 16')
        return

    # Teste 2: gravação como o app (com VAD)
    print('\n--- Teste 2: gravação como o app (VAD) ---')
    try:
        app_audio, speech_detected = record_like_app(
            device,
            config['sample_rate'],
            config['silence_duration'],
            config['recording_mode'],
        )
        stats = analyze_audio(app_audio, config['sample_rate'])
        path = os.path.join(OUTPUT_DIR, 'test_app_logic.wav')
        save_wav(path, app_audio, config['sample_rate'])
        print(f'Arquivo salvo: {path}')
        print_diagnosis(stats, speech_detected, config['min_duration'], config['recording_mode'])
    except Exception as e:
        print(f'ERRO no teste VAD: {e}')
        return

    # Teste 3: transcrição opcional
    if args.full and not stats['silent']:
        print('\n--- Teste 3: transcrição ---')
        try:
            test_transcription(app_audio, config['sample_rate'], config)
        except Exception as e:
            print(f'ERRO na transcrição: {e}')
            import traceback
            traceback.print_exc()
    elif args.full:
        print('\n--- Teste 3: transcrição ignorada (áudio silencioso) ---')

    print('\n=== Fim do teste ===')
    print('Ouça os arquivos em scripts/test_output/ para confirmar se sua voz foi gravada.')
    print('Teste com transcrição: poetry run python scripts/test_mic.py --full')


if __name__ == '__main__':
    main()
