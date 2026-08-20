import io
import os

import ctypes
import ctypes.util
import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from openai import OpenAI

from utils import ConfigManager
from text_processing import process_transcription


def _cuda_libraries_available():
    """Verifica se as bibliotecas CUDA necessárias ao CTranslate2 podem ser carregadas."""
    try:
        import ctranslate2
        path = ctypes.util.find_library("cublas")
        if path:
            try:
                ctypes.CDLL(path)
                return True
            except OSError:
                pass

        for lib_name in ("libcublas.so.12", "libcublas.so"):
            try:
                ctypes.CDLL(lib_name)
                return True
            except OSError:
                pass
        return False
    except Exception as e:
        ConfigManager.console_print(
            f"Falha ao verificar CUDA: {e}"
        )
        return False


def _resolve_device(requested_device):
    if requested_device == 'cpu':
        return 'cpu'
    if requested_device in ('cuda', 'auto'):
        if _cuda_libraries_available():
            return 'cuda'
        if requested_device == 'cuda':
            ConfigManager.console_print(
                'CUDA configurado mas bibliotecas NVIDIA (libcublas) não encontradas. Usando CPU.'
            )
        else:
            ConfigManager.console_print('GPU indisponível, usando CPU.')
        return 'cpu'
    return requested_device


def _build_whisper_model(local_model_options, device, compute_type, model_path=None):
    if model_path:
        ConfigManager.console_print(f'Carregando modelo de: {model_path} em {device}')
        return WhisperModel(
            model_path,
            device=device,
            compute_type=compute_type,
            download_root=None,
        )
    return WhisperModel(
        local_model_options['model'],
        device=device,
        compute_type=compute_type,
    )


def create_local_model():
    """Cria um modelo local usando a biblioteca faster-whisper."""
    ConfigManager.console_print('Criando modelo local...')
    local_model_options = ConfigManager.get_config_section('model_options')['local']
    compute_type = local_model_options['compute_type']
    model_path = local_model_options.get('model_path')

    if compute_type == 'int8':
        device = 'cpu'
        ConfigManager.console_print('Usando quantização int8, forçando uso da CPU.')
    else:
        device = _resolve_device(local_model_options['device'])

    try:
        model = _build_whisper_model(local_model_options, device, compute_type, model_path)
    except Exception as e:
        ConfigManager.console_print(f'Erro ao inicializar WhisperModel: {e}')
        ConfigManager.console_print('Retornando para CPU.')
        device = 'cpu'
        model = _build_whisper_model(local_model_options, device, compute_type, model_path)

    ConfigManager.console_print(f'Modelo local criado em {device}.')
    return model


def _is_gpu_runtime_error(error):
    message = str(error).lower()
    return any(token in message for token in ('cuda', 'cublas', 'cudnn', 'cudart'))


def _run_local_transcription(local_model, audio_data_float, model_options):
    response = local_model.transcribe(
        audio=audio_data_float,
        language=model_options['common']['language'],
        initial_prompt=model_options['common']['initial_prompt'],
        condition_on_previous_text=model_options['local']['condition_on_previous_text'],
        temperature=model_options['common']['temperature'],
        vad_filter=model_options['local']['vad_filter'],
    )
    return ''.join(segment.text for segment in response[0])


def transcribe_local(audio_data, local_model=None):
    """
    Transcreve um arquivo de áudio usando um modelo local.

    Retorna:
        tuple[str, WhisperModel | None]: texto da transcrição e o modelo usado
    """
    if not local_model:
        local_model = create_local_model()
    model_options = ConfigManager.get_config_section('model_options')
    audio_data_float = audio_data.astype(np.float32) / 32768.0

    try:
        text = _run_local_transcription(local_model, audio_data_float, model_options)
        return text, local_model
    except RuntimeError as e:
        if not _is_gpu_runtime_error(e):
            raise
        ConfigManager.console_print(f'Erro na transcrição via GPU: {e}')
        ConfigManager.console_print('Recarregando modelo na CPU...')
        local_model_options = model_options['local']
        local_model = _build_whisper_model(
            local_model_options,
            'cpu',
            local_model_options['compute_type'],
            local_model_options.get('model_path'),
        )
        text = _run_local_transcription(local_model, audio_data_float, model_options)
        return text, local_model


def transcribe_api(audio_data):
    """Transcreve um arquivo de áudio usando a API da OpenAI."""
    model_options = ConfigManager.get_config_section('model_options')
    client = OpenAI(
        api_key=os.getenv('OPENAI_API_KEY') or None,
        base_url=model_options['api']['base_url'] or 'https://api.openai.com/v1'
    )

    byte_io = io.BytesIO()
    sample_rate = ConfigManager.get_config_section('recording_options').get('sample_rate') or 16000
    sf.write(byte_io, audio_data, sample_rate, format='wav')
    byte_io.seek(0)

    response = client.audio.transcriptions.create(
        model=model_options['api']['model'],
        file=('audio.wav', byte_io, 'audio/wav'),
        language=model_options['common']['language'],
        prompt=model_options['common']['initial_prompt'],
        temperature=model_options['common']['temperature'],
    )
    return response.text


def post_process_transcription(transcription):
    """Aplica pós-processamento à transcrição (legado — preferir process_transcription)."""
    processed = process_transcription(transcription)
    if processed.kind == 'keys':
        return processed
    if processed.kind == 'empty':
        return ''
    return processed.text


def transcribe(audio_data, local_model=None):
    """
    Transcreve dados de áudio usando a API da OpenAI ou um modelo local, conforme a configuração.

    Retorna:
        tuple[ProcessedTranscription, WhisperModel | None]
    """
    if audio_data is None:
        return process_transcription(''), local_model

    if ConfigManager.get_config_value('model_options', 'use_api'):
        transcription = transcribe_api(audio_data)
        return process_transcription(transcription), local_model

    transcription, local_model = transcribe_local(audio_data, local_model)
    return process_transcription(transcription), local_model
