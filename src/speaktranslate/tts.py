import asyncio
import os
import subprocess
import tempfile
import wave
from pathlib import Path

import edge_tts
import numpy as np
import soundfile as sf
import sounddevice as sd

# Uma voz neural masculina padrão por idioma (confirmado via
# `edge-tts --list-voices`, que já rotula Male/Female em cada voz — motor com
# metadado de gênero oficial, diferente do Piper/Kokoro). Ver esse comando
# para outras opções, inclusive femininas.
_DEFAULT_VOICES = {
    'pt': 'pt-BR-AntonioNeural',
    'en': 'en-US-GuyNeural',
    'es': 'es-ES-AlvaroNeural',
    'fr': 'fr-FR-HenriNeural',
    'de': 'de-DE-ConradNeural',
    'it': 'it-IT-DiegoNeural',
    'ja': 'ja-JP-KeitaNeural',
    'ko': 'ko-KR-InJoonNeural',
    'ru': 'ru-RU-DmitryNeural',
    'zh': 'zh-CN-YunyangNeural',
}

# Vozes Piper (offline) por idioma. Qualidade "medium" — bom equilíbrio entre
# naturalidade e velocidade em CPU. Japonês não tem voz oficial disponível no
# catálogo do Piper no momento.
#
# Sobre gênero: o Piper não publica esse metadado (nem no voices.json, nem
# nos MODEL_CARDs) — confirmamos pt/de/ru (faber/thorsten/denis) e it (via
# riccardo) com uma fonte externa (tts.ai); en trocado de "lessac" (gênero
# contestado em fóruns) para "ryan" (masculino, confirmação mais consistente).
# es (davefx) é uma aposta razoável pelo nome, não confirmada. fr (siwis) e ko
# (kss) não têm NENHUMA alternativa masculina no catálogo atual — ambas ficam
# femininas por falta de opção. it (paola) e zh (huayan) continuam femininas
# de propósito: a única alternativa masculina confirmada de it ("riccardo")
# só existe em qualidade x_low (pior), e a de zh ("chaowen") não tem gênero
# confirmado — ver conversa de decisão no histórico do projeto.
_PIPER_VOICES = {
    'pt': 'pt_BR-faber-medium',
    'en': 'en_US-ryan-medium',
    'es': 'es_ES-davefx-medium',
    'fr': 'fr_FR-siwis-medium',
    'de': 'de_DE-thorsten-medium',
    'it': 'it_IT-paola-medium',
    'ko': 'ko_KR-kss-medium',
    'ru': 'ru_RU-denis-medium',
    'zh': 'zh_CN-huayan-medium',
}

PIPER_VOICES_DIR = Path.home() / '.cache' / 'speaktranslate' / 'piper_voices'

# Idioma do app -> código de idioma do Kokoro (https://huggingface.co/hexgrad/Kokoro-82M).
# Sem suporte a russo, alemão nem coreano no momento. Japonês também não está
# incluído de propósito: dependeria do extra "misaki[ja]", que traz o
# pyopenjtalk (extensão nativa C/C++ via cmake) — removido do projeto por
# falhar ao compilar em alguns toolchains de Xcode (ver pyproject.toml).
_KOKORO_LANGS = {
    'en': 'a',
    'es': 'e',
    'fr': 'f',
    'it': 'i',
    'pt': 'p',
    'zh': 'z',
}

# Catálogo de vozes por idioma (ver VOICES.md do modelo, nomes af_/am_ etc. =
# feminina/masculina — gênero explícito no próprio nome, ao contrário do
# Piper). A primeira da lista é a usada por padrão quando nenhuma voz
# específica é escolhida (ver `speak()`/`speak_to_device()`) — masculina em
# todo idioma que tiver uma, exceto francês, que só tem a feminina ff_siwis
# no catálogo atual do Kokoro (sem alternativa).
_KOKORO_VOICES = {
    'en': [
        'am_michael', 'am_fenrir', 'am_puck', 'am_echo', 'am_eric', 'am_liam', 'am_onyx', 'am_santa', 'am_adam',
        'af_heart', 'af_bella', 'af_nicole', 'af_aoede', 'af_kore', 'af_sarah', 'af_nova', 'af_alloy',
        'af_sky', 'af_jessica', 'af_river',
    ],
    'es': ['em_alex', 'em_santa', 'ef_dora'],
    'fr': ['ff_siwis'],
    'it': ['im_nicola', 'if_sara'],
    'pt': ['pm_alex', 'pm_santa', 'pf_dora'],
    'zh': [
        'zm_yunjian', 'zm_yunxi', 'zm_yunxia', 'zm_yunyang',
        'zf_xiaobei', 'zf_xiaoni', 'zf_xiaoxiao', 'zf_xiaoyi',
    ],
}
KOKORO_SAMPLE_RATE = 24000

ENGINES = ('edge', 'piper', 'kokoro')
DEFAULT_ENGINE = 'piper'

SYNTHESIS_TIMEOUT_S = 20
PLAYBACK_TIMEOUT_S = 60

_piper_voices_cache = {}  # nome da voz -> instância PiperVoice já carregada
_kokoro_pipelines_cache = {}  # código de idioma do Kokoro -> KPipeline já carregado


def voice_for_language(lang_code, fallback='en-US-GuyNeural'):
    return _DEFAULT_VOICES.get(lang_code, fallback)


def piper_voice_available(lang_code):
    return lang_code in _PIPER_VOICES


def kokoro_voice_available(lang_code):
    return lang_code in _KOKORO_LANGS


def kokoro_voices_for_lang(lang_code):
    """Lista de vozes Kokoro disponíveis para um idioma (a primeira é a
    padrão), ou lista vazia se o idioma não tiver suporte no Kokoro."""
    return list(_KOKORO_VOICES.get(lang_code, []))


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


def _load_kokoro_pipeline(kokoro_lang_code):
    if kokoro_lang_code in _kokoro_pipelines_cache:
        return _kokoro_pipelines_cache[kokoro_lang_code]

    # Import tardio: o pacote "kokoro" (e o espeak-ng que ele usa por baixo
    # para idiomas além do inglês) só é necessário se este motor for usado.
    # Baixa os pesos do modelo (~327MB) do Hugging Face Hub na primeira vez
    # que um idioma é usado, e fica em cache local (~/.cache/huggingface/)
    # depois disso.
    try:
        from kokoro import KPipeline
    except ImportError as exc:
        raise RuntimeError(
            'Pacote "kokoro" não instalado. Ele requer Python 3.11 ou 3.12 — a dependência '
            '"misaki" ainda não dá suporte a Python 3.13+ (ver pyproject.toml e o README, seção '
            '"Texto-para-voz"). Recrie a venv do projeto com `poetry env use 3.12` (ou 3.11) e '
            'rode `poetry install` de novo, ou use o motor "Piper (local)"/"Edge (nuvem)".') from exc

    pipeline = KPipeline(lang_code=kokoro_lang_code)
    _kokoro_pipelines_cache[kokoro_lang_code] = pipeline
    return pipeline


def _synthesize_to_file(text, lang_code, engine, voice=None):
    """Sintetiza `text` num arquivo de áudio temporário e retorna o caminho
    (não reproduz). `voice` só tem efeito com engine="kokoro" (ver
    `kokoro_voices_for_lang()`); ignorado pelos outros motores, que já
    escolhem a própria voz por idioma."""
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

    if engine == 'kokoro':
        kokoro_lang_code = _KOKORO_LANGS.get(lang_code)
        available_voices = _KOKORO_VOICES.get(lang_code)
        if kokoro_lang_code is None or not available_voices:
            raise ValueError(f'Kokoro não tem voz disponível para o idioma "{lang_code}".')
        voice_name = voice or available_voices[0]
        pipeline = _load_kokoro_pipeline(kokoro_lang_code)

        # pipeline() divide o texto em frases e gera um pedaço de áudio por
        # frase (generator); concatenamos tudo num único arquivo.
        chunks = [audio for _, _, audio in pipeline(text, voice=voice_name)]
        if not chunks:
            raise RuntimeError('Kokoro não gerou áudio para o texto.')
        audio = chunks[0] if len(chunks) == 1 else np.concatenate(chunks)

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            output_path = tmp_file.name
        sf.write(output_path, audio, KOKORO_SAMPLE_RATE)
        return output_path

    raise ValueError(f'Motor de voz desconhecido: {engine!r} (use "edge", "piper" ou "kokoro")')


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


def speak(text, lang_code, engine=DEFAULT_ENGINE, voice=None):
    """
    Sintetiza o texto em áudio e reproduz no dispositivo de saída padrão.

    :param engine: 'edge' (edge-tts, nuvem, vozes neurais), 'piper' (offline,
        100% local — baixa o modelo de voz na primeira vez que um idioma é
        usado e fica em cache em ~/.cache/speaktranslate/piper_voices/) ou
        'kokoro' (offline, 100% local, modelo maior/mais pesado — baixa os
        pesos do Hugging Face Hub na primeira vez que um idioma é usado; sem
        voz para russo, alemão e coreano).
    :param voice: nome de uma voz específica (só tem efeito com
        engine="kokoro" — ver `kokoro_voices_for_lang()`); None usa a voz
        padrão do idioma.
    """
    if not text:
        return
    path = _synthesize_to_file(text, lang_code, engine, voice=voice)
    try:
        _play_file(path)
    finally:
        os.remove(path)


def speak_to_device(text, lang_code, device, engine=DEFAULT_ENGINE, voice=None):
    """
    Sintetiza o texto em áudio e reproduz num dispositivo de saída
    específico, em vez do dispositivo padrão — usado para "fingir" ser um
    microfone dentro de um app de chamada (ex.: tocando num driver de
    loopback como o BlackHole, configurado como microfone no Zoom/Meet/Teams):
    quem está na chamada ouve, mas quem está rodando o app não.

    :param device: índice do dispositivo de saída (ver `sounddevice.query_devices()`).
    :param engine: 'edge', 'piper' ou 'kokoro', ver `speak()`.
    :param voice: ver `speak()`.
    """
    if not text:
        return
    path = _synthesize_to_file(text, lang_code, engine, voice=voice)
    try:
        _play_file_on_device(path, device)
    finally:
        os.remove(path)
