import time
import traceback
import numpy as np
import sounddevice as sd
import tempfile
import wave
import webrtcvad
from PyQt5.QtCore import QThread, QMutex, pyqtSignal
from collections import deque
from threading import Event

from transcription import transcribe
from audio_processing import enhance_recording
from utils import ConfigManager, resolve_record_sample_rate, resample_audio

NUM_VISUALIZER_BARS = 8


class ResultThread(QThread):
    """
    Thread para gravação de áudio, transcrição e processamento do resultado.

    Gerencia todo o processo de:
    1. Gravar áudio do microfone
    2. Detectar fala e silêncio
    3. Salvar o áudio gravado como array numpy
    4. Transcrever o áudio
    5. Emitir o resultado da transcrição

    Sinais:
        statusSignal: Emite o status atual da thread (ex.: 'recording', 'transcribing', 'idle')
        resultSignal: Emite o resultado da transcrição
    """

    statusSignal = pyqtSignal(str)
    resultSignal = pyqtSignal(object)
    audioLevelSignal = pyqtSignal(list)

    def __init__(self, local_model=None):
        """
        Inicializa a ResultThread.

        :param local_model: Modelo local de transcrição (se aplicável)
        """
        super().__init__()
        self.local_model = local_model
        self.is_recording = False
        self.is_running = True
        self.sample_rate = None
        self.mutex = QMutex()

    def stop_recording(self):
        """Para a sessão de gravação atual."""
        self.mutex.lock()
        self.is_recording = False
        self.mutex.unlock()

    def stop(self):
        """Para a execução completa da thread."""
        self.mutex.lock()
        self.is_running = False
        self.mutex.unlock()
        self.statusSignal.emit('idle')
        self.wait()

    def run(self):
        """Método principal de execução da thread."""
        try:
            if not self.is_running:
                return

            self.mutex.lock()
            self.is_recording = True
            self.mutex.unlock()

            self.statusSignal.emit('recording')
            ConfigManager.console_print('Gravando...')
            audio_data = self._record_audio()

            if not self.is_running:
                return

            if audio_data is None:
                self.statusSignal.emit('idle')
                return

            self.statusSignal.emit('transcribing')
            ConfigManager.console_print('Transcrevendo...')

            start_time = time.time()
            result, self.local_model = transcribe(audio_data, self.local_model)
            end_time = time.time()

            transcription_time = end_time - start_time
            if result.kind == 'keys':
                ConfigManager.console_print(
                    f'Transcrição concluída em {transcription_time:.2f} segundos. '
                    f'Comando de voz: {result.keys}'
                )
            elif result.kind == 'text':
                ConfigManager.console_print(
                    f'Transcrição concluída em {transcription_time:.2f} segundos. '
                    f'Linha pós-processada: {result.text}'
                )
            else:
                ConfigManager.console_print(
                    f'Transcrição concluída em {transcription_time:.2f} segundos. '
                    f'Sem conteúdo para inserir.'
                )

            if not self.is_running:
                return

            self.statusSignal.emit('idle')
            self.resultSignal.emit(result)

        except Exception as e:
            traceback.print_exc()
            self.statusSignal.emit('error')
            from text_processing import ProcessedTranscription
            self.resultSignal.emit(ProcessedTranscription(kind='empty'))
        finally:
            self.stop_recording()

    @staticmethod
    def _compute_bar_levels(frame, num_bars=NUM_VISUALIZER_BARS):
        if frame.size < 64:
            return [0.0] * num_bars

        samples = frame.astype(np.float32) / 32768.0
        window = np.hanning(len(samples))
        spectrum = np.abs(np.fft.rfft(samples * window))
        if spectrum.size == 0:
            return [0.0] * num_bars

        band_size = max(1, spectrum.size // num_bars)
        levels = []
        for index in range(num_bars):
            start = index * band_size
            end = min(spectrum.size, start + band_size)
            chunk = spectrum[start:end]
            energy = float(np.sqrt(np.mean(chunk ** 2))) if chunk.size else 0.0
            levels.append(min(1.0, energy * 10.0))
        return levels

    def _record_audio(self):
        """
        Grava áudio do microfone.

        :return: array numpy com os dados de áudio, ou None se a gravação for muito curta
        """
        recording_options = ConfigManager.get_config_section('recording_options')
        target_sample_rate = recording_options.get('sample_rate') or 16000
        device = recording_options.get('sound_device')
        record_sample_rate = resolve_record_sample_rate(device, target_sample_rate)
        if record_sample_rate != target_sample_rate:
            ConfigManager.console_print(
                f'Dispositivo não suporta {target_sample_rate}Hz; gravando a {record_sample_rate}Hz.'
            )

        self.sample_rate = record_sample_rate
        frame_duration_ms = 30  # duração de quadro de 30ms para WebRTC VAD
        frame_size = int(self.sample_rate * (frame_duration_ms / 1000.0))
        silence_duration_ms = recording_options.get('silence_duration') or 900
        silence_frames = int(silence_duration_ms / frame_duration_ms)

        # Atraso de 150ms antes de iniciar o VAD para evitar confundir o som da tecla com voz
        initial_frames_to_skip = int(0.15 * self.sample_rate / frame_size)

        recording_mode = recording_options.get('recording_mode') or 'continuous'
        vad = None
        if recording_mode in ('voice_activity_detection', 'continuous'):
            vad = webrtcvad.Vad(2)  # agressividade do VAD: 0 a 3, sendo 3 a mais agressiva
            speech_detected = False
            silent_frame_count = 0

        audio_buffer = deque(maxlen=frame_size)
        recording = []

        data_ready = Event()

        def audio_callback(indata, frames, time, status):
            if status:
                ConfigManager.console_print(f'Status do callback de áudio: {status}')
            audio_buffer.extend(indata[:, 0])
            data_ready.set()

        with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='int16',
                            blocksize=frame_size, device=device,
                            callback=audio_callback):
            while self.is_running and self.is_recording:
                data_ready.wait()
                data_ready.clear()

                if len(audio_buffer) < frame_size:
                    continue

                frame = np.array(list(audio_buffer), dtype=np.int16)
                audio_buffer.clear()
                recording.extend(frame)

                if ConfigManager.get_config_value('misc', 'show_audio_visualizer'):
                    self.audioLevelSignal.emit(self._compute_bar_levels(frame))

                if initial_frames_to_skip > 0:
                    initial_frames_to_skip -= 1
                    continue

                if vad:
                    if vad.is_speech(frame.tobytes(), self.sample_rate):
                        silent_frame_count = 0
                        if not speech_detected:
                            ConfigManager.console_print('Fala detectada.')
                            speech_detected = True
                    else:
                        silent_frame_count += 1

                    if speech_detected and silent_frame_count > silence_frames:
                        break

        audio_data = np.array(recording, dtype=np.int16)
        if record_sample_rate != target_sample_rate:
            audio_data = resample_audio(audio_data, record_sample_rate, target_sample_rate)

        audio_data = enhance_recording(audio_data, target_sample_rate)

        duration = len(audio_data) / target_sample_rate

        ConfigManager.console_print(
            f'Gravação finalizada. Tamanho: {audio_data.size} amostras, Duração: {duration:.2f} segundos'
        )

        min_duration_ms = recording_options.get('min_duration') or 100

        if (duration * 1000) < min_duration_ms:
            ConfigManager.console_print('Descartada por ser muito curta.')
            return None

        return audio_data
