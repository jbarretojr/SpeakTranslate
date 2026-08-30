import asyncio
import os
import subprocess
import tempfile
import wave
from pathlib import Path

import edge_tts

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


def _speak_piper(text, lang_code):
    voice_name = _PIPER_VOICES.get(lang_code)
    if voice_name is None:
        raise ValueError(f'Piper não tem voz disponível para o idioma "{lang_code}".')

    voice = _load_piper_voice(voice_name)

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
        output_path = tmp_file.name
    try:
        with wave.open(output_path, 'wb') as wav_file:
            voice.synthesize_wav(text, wav_file)
        subprocess.run(['afplay', output_path], timeout=PLAYBACK_TIMEOUT_S, check=True)
    finally:
        os.remove(output_path)


def _speak_edge(text, lang_code):
    voice = voice_for_language(lang_code)

    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
        output_path = tmp_file.name
    try:
        asyncio.run(_synthesize_edge(text, voice, output_path))
        subprocess.run(['afplay', output_path], timeout=PLAYBACK_TIMEOUT_S, check=True)
    finally:
        os.remove(output_path)


def speak(text, lang_code, engine=DEFAULT_ENGINE):
    """
    Sintetiza o texto em áudio e reproduz no dispositivo de saída padrão.

    :param engine: 'edge' (edge-tts, nuvem, vozes neurais) ou 'piper'
        (offline, 100% local — baixa o modelo de voz na primeira vez que um
        idioma é usado e fica em cache em ~/.cache/speaktranslate/piper_voices/).
    """
    if not text:
        return

    if engine == 'piper':
        _speak_piper(text, lang_code)
    elif engine == 'edge':
        _speak_edge(text, lang_code)
    else:
        raise ValueError(f'Motor de voz desconhecido: {engine!r} (use "edge" ou "piper")')
