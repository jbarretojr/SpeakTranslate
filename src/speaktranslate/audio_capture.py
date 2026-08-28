import numpy as np
import sounddevice as sd
import webrtcvad
from collections import deque
from threading import Event, Lock

FRAME_DURATION_MS = 30
VAD_AGGRESSIVENESS = 2
INITIAL_SILENCE_SKIP_S = 0.15


def record_utterance(sample_rate=16000, device=None, silence_duration_ms=900,
                      min_duration_ms=250, max_duration_s=30, stop_event=None):
    """
    Grava áudio do microfone até detectar uma pausa na fala (VAD) ou atingir a
    duração máxima.

    :param stop_event: threading.Event opcional; quando definido, interrompe a
        gravação em andamento (retorna None).
    Retorna:
        np.ndarray (int16) com o áudio gravado, ou None se não houve fala
        suficiente para processar.
    """
    frame_size = int(sample_rate * (FRAME_DURATION_MS / 1000.0))
    silence_frames = int(silence_duration_ms / FRAME_DURATION_MS)
    initial_frames_to_skip = int(INITIAL_SILENCE_SKIP_S * sample_rate / frame_size)
    max_frames = int(max_duration_s * 1000 / FRAME_DURATION_MS)

    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
    speech_detected = False
    silent_frame_count = 0
    frame_count = 0

    audio_buffer = deque(maxlen=frame_size)
    recording = []
    data_ready = Event()

    def audio_callback(indata, frames, time, status):
        audio_buffer.extend(indata[:, 0])
        data_ready.set()

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype='int16',
                         blocksize=frame_size, device=device,
                         callback=audio_callback):
        while True:
            if stop_event is not None and stop_event.is_set():
                return None

            if not data_ready.wait(timeout=0.2):
                continue
            data_ready.clear()

            if len(audio_buffer) < frame_size:
                continue

            frame = np.array(list(audio_buffer), dtype=np.int16)
            audio_buffer.clear()
            recording.extend(frame)
            frame_count += 1

            if initial_frames_to_skip > 0:
                initial_frames_to_skip -= 1
                continue

            if vad.is_speech(frame.tobytes(), sample_rate):
                silent_frame_count = 0
                speech_detected = True
            else:
                silent_frame_count += 1

            if speech_detected and silent_frame_count > silence_frames:
                break
            if frame_count > max_frames:
                break

    audio_data = np.array(recording, dtype=np.int16)
    duration_ms = (len(audio_data) / sample_rate) * 1000

    if not speech_detected or duration_ms < min_duration_ms:
        return None

    return audio_data


def list_input_devices():
    return sd.query_devices()


class ContinuousAudioCapture:
    """
    Captura de áudio contínua (sem detecção de pausa/fim de fala), usada pela
    transcrição em streaming: mantém um stream de entrada aberto e acumula o
    áudio recebido; quem consome (`read_available`) decide quando e quanto
    processar, em vez de esperar uma pausa na fala para começar.
    """

    def __init__(self, sample_rate=16000, device=None):
        self.sample_rate = sample_rate
        self._lock = Lock()
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=sample_rate, channels=1, dtype='int16',
            device=device, callback=self._on_audio,
        )

    def _on_audio(self, indata, frames, time_info, status):
        with self._lock:
            self._chunks.append(indata[:, 0].copy())

    def start(self):
        self._stream.start()

    def stop(self):
        self._stream.stop()
        self._stream.close()

    def read_available(self):
        """Retorna (e remove do buffer interno) todo áudio acumulado desde a última leitura."""
        with self._lock:
            if not self._chunks:
                return np.empty(0, dtype=np.int16)
            chunks, self._chunks = self._chunks, []
        return np.concatenate(chunks)
