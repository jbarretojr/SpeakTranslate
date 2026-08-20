import numpy as np
from faster_whisper import WhisperModel


def create_model(model_size='base', device='auto', compute_type='default'):
    """Carrega o modelo faster-whisper usado para detecção de idioma e transcrição."""
    return WhisperModel(model_size, device=device, compute_type=compute_type)


def transcribe(model, audio_data, language=None):
    """
    Transcreve áudio e detecta o idioma falado.

    :param audio_data: np.ndarray (int16) com o áudio gravado
    :param language: código ISO-639-1 para forçar o idioma; None para detectar automaticamente
    :return: tupla (texto transcrito, código do idioma detectado, probabilidade)
    """
    audio_float = audio_data.astype(np.float32) / 32768.0

    segments, info = model.transcribe(audio_float, language=language)
    text = ''.join(segment.text for segment in segments).strip()

    return text, info.language, info.language_probability
