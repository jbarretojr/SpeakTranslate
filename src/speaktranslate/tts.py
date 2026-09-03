import asyncio
import os
import subprocess
import tempfile
import wave
from pathlib import Path

import edge_tts
import soundfile as sf
import sounddevice as sd

# Uma voz neural padrão por idioma. Ver `edge-tts --list-voices` para outras opções.
_DEFAULT_VOICES = {
    'pt': 'pt-BR-FranciscaNeural',
    'en': 'en-US-AriaNeural',
    'es': 'es-ES-ElviraNeural',
    'fr': 'fr-FR-DeniseNeural',
    'de': 'de-DE-KatjaNeural',
    'it': 'it-IT-ElsaNeural',
    'ja': 'ja-JP-NanamiNeural',
    'ko': 'ko-KR-SunHiNeural',
    'ru': 'ru-RU-SvetlanaNeural',
    'zh': 'zh-CN-XiaoxiaoNeural',
}

# Vozes Piper (offline) por idioma. Qualidade "medium" — bom equilíbrio entre
# naturalidade e velocidade em CPU. Japonês não tem voz oficial disponível no
# catálogo do Piper no momento.
_PIPER_VOICES = {
    'pt': 'pt_BR-faber-medium',
    'en': 'en_US-lessac-medium',
    'es': 'es_ES-davefx-medium',
    'fr': 'fr_FR-siwis-medium',
    'de': 'de_DE-thorsten-medium',
    'it': 'it_IT-paola-medium',
    'ko': 'ko_KR-kss-medium',
    'ru': 'ru_RU-denis-medium',
    'zh': 'zh_CN-huayan-medium',
}

PIPER_VOICES_DIR = Path.home() / '.cache' / 'speaktranslate' / 'piper_voices'

ENGINES = ('edge', 'piper')
DEFAULT_ENGINE = 'piper'

SYNTHESIS_TIMEOUT_S = 20
PLAYBACK_TIMEOUT_S = 60

_piper_voices_cache = {}  # nome da voz -> instância PiperVoice já carregada


def voice_for_language(lang_code, fallback='en-US-AriaNeural'):
    return _DEFAULT_VOICES.get(lang_code, fallback)


def piper_voice_available(lang_code):
    return lang_code in _PIPER_VOICES


async def _synthesize_edge(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await asyncio.wait_for(communicate.save(output_path), timeout=SYNTHESIS_TIMEOUT_S)


def _load_piper_voice(voice_name):
    if voice_name in _piper_voices_cache:
        return _piper_voices_cache[voice_name]

    from piper import PiperVoice
    from piper.download_voices import download_voice

    model_path = PIPER_VOICES_DIR / f'{voice_name}.onnx'
    if not model_path.exists():
        PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
        download_voice(voice_name, PIPER_VOICES_DIR)

    voice = PiperVoice.load(str(model_path))
    _piper_voices_cache[voice_name] = voice
    return voice


def _synthesize_to_file(text, lang_code, engine):
    """Sintetiza `text` num arquivo de áudio temporário e retorna o caminho (não reproduz)."""
    if engine == 'piper':
        voice_name = _PIPER_VOICES.get(lang_code)
        if voice_name is None:
            raise ValueError(f'Piper não tem voz disponível para o idioma "{lang_code}".')
        voice = _load_piper_voice(voice_name)

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            output_path = tmp_file.name
        with wave.open(output_path, 'wb') as wav_file:
            voice.synthesize_wav(text, wav_file)
        return output_path

    if engine == 'edge':
        voice = voice_for_language(lang_code)
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
            output_path = tmp_file.name
        asyncio.run(_synthesize_edge(text, voice, output_path))
        return output_path

    raise ValueError(f'Motor de voz desconhecido: {engine!r} (use "edge" ou "piper")')


def _play_file(path):
    """Reproduz um arquivo de áudio no dispositivo de saída padrão do sistema."""
    subprocess.run(['afplay', path], timeout=PLAYBACK_TIMEOUT_S, check=True)


def _play_file_on_device(path, device):
    """
    Reproduz um arquivo de áudio num dispositivo de saída específico (ex.: um
    driver de áudio virtual como o BlackHole), em vez do dispositivo padrão.
    """
    data, samplerate = sf.read(path, dtype='float32')
    sd.play(data, samplerate, device=device)
    sd.wait()


def speak(text, lang_code, engine=DEFAULT_ENGINE):
    """
    Sintetiza o texto em áudio e reproduz no dispositivo de saída padrão.

    :param engine: 'edge' (edge-tts, nuvem, vozes neurais) ou 'piper'
        (offline, 100% local — baixa o modelo de voz na primeira vez que um
        idioma é usado e fica em cache em ~/.cache/speaktranslate/piper_voices/).
    """
    if not text:
        return
    path = _synthesize_to_file(text, lang_code, engine)
    try:
        _play_file(path)
    finally:
        os.remove(path)


def speak_to_device(text, lang_code, device, engine=DEFAULT_ENGINE):
    """
    Sintetiza o texto em áudio e reproduz num dispositivo de saída
    específico, em vez do dispositivo padrão — usado para "fingir" ser um
    microfone dentro de um app de chamada (ex.: tocando num driver de
    loopback como o BlackHole, configurado como microfone no Zoom/Meet/Teams):
    quem está na chamada ouve, mas quem está rodando o app não.

    :param device: índice do dispositivo de saída (ver `sounddevice.query_devices()`).
    :param engine: 'edge' ou 'piper', ver `speak()`.
    """
    if not text:
        return
    path = _synthesize_to_file(text, lang_code, engine)
    try:
        _play_file_on_device(path, device)
    finally:
        os.remove(path)
