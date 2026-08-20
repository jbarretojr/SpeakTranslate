import asyncio
import os
import tempfile

import edge_tts
from playsound import playsound

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


def voice_for_language(lang_code, fallback='en-US-AriaNeural'):
    return _DEFAULT_VOICES.get(lang_code, fallback)


async def _synthesize(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def speak(text, lang_code):
    """Sintetiza o texto em áudio (edge-tts) e reproduz no dispositivo de saída padrão."""
    if not text:
        return

    voice = voice_for_language(lang_code)

    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
        output_path = tmp_file.name

    try:
        asyncio.run(_synthesize(text, voice, output_path))
        playsound(output_path)
    finally:
        os.remove(output_path)
