import numpy as np
from scipy.signal import butter, sosfilt

from utils import ConfigManager


def _to_float32(audio_data):
    return audio_data.astype(np.float32) / 32768.0


def _to_int16(audio_float):
    return np.clip(audio_float * 32768.0, -32768, 32767).astype(np.int16)


def highpass_filter(audio_float, sample_rate, cutoff_hz=80.0, order=2):
    """Remove rumble e ruído de baixa frequência (ventilador, mesa, HVAC)."""
    nyquist = sample_rate / 2.0
    if cutoff_hz <= 0 or cutoff_hz >= nyquist:
        return audio_float

    sos = butter(order, cutoff_hz, btype='highpass', fs=sample_rate, output='sos')
    return sosfilt(sos, audio_float).astype(np.float32)


def spectral_noise_reduce(
    audio_float,
    sample_rate,
    noise_profile_ms=300,
    strength=0.75,
    n_fft=512,
):
    """
    Redução espectral de ruído estacionário.

    Estima o perfil de ruído a partir do início da gravação (período antes/entre
    a fala, incluindo o clique do atalho) e atenua frequências abaixo desse perfil.
    """
    if strength <= 0 or audio_float.size < n_fft:
        return audio_float

    hop = n_fft // 2
    window = np.hanning(n_fft).astype(np.float32)

    profile_samples = int(sample_rate * noise_profile_ms / 1000.0)
    profile_samples = max(n_fft, min(profile_samples, len(audio_float) // 2))
    noise_segment = audio_float[:profile_samples]

    noise_frames = []
    for start in range(0, len(noise_segment) - n_fft + 1, hop):
        frame = noise_segment[start:start + n_fft] * window
        noise_frames.append(np.abs(np.fft.rfft(frame)))

    if not noise_frames:
        return audio_float

    noise_profile = np.mean(noise_frames, axis=0)
    noise_floor = np.max(noise_profile) * 0.02

    output = np.zeros(len(audio_float) + n_fft, dtype=np.float32)
    window_sum = np.zeros(len(audio_float) + n_fft, dtype=np.float32)

    for start in range(0, len(audio_float) - n_fft + 1, hop):
        frame = audio_float[start:start + n_fft] * window
        spectrum = np.fft.rfft(frame)
        magnitude = np.abs(spectrum)
        phase = np.angle(spectrum)

        attenuated = magnitude - (noise_profile * strength)
        attenuated = np.maximum(attenuated, magnitude * (1.0 - strength))
        attenuated = np.maximum(attenuated, noise_floor)

        clean_frame = np.fft.irfft(attenuated * np.exp(1j * phase), n=n_fft).real * window
        output[start:start + n_fft] += clean_frame
        window_sum[start:start + n_fft] += window ** 2

    window_sum = np.maximum(window_sum[:len(audio_float)], 1e-8)
    return (output[:len(audio_float)] / window_sum).astype(np.float32)


def normalize_peak(audio_float, target_peak=0.9):
    """Normaliza o pico do sinal para melhorar a entrada do Whisper."""
    peak = float(np.max(np.abs(audio_float)))
    if peak < 1e-6:
        return audio_float
    return (audio_float * (target_peak / peak)).astype(np.float32)


def enhance_recording(audio_data, sample_rate):
    """
    Aplica melhorias de áudio configuradas antes da transcrição.

    Pipeline: passa-alta → redução de ruído → normalização de pico.
    """
    options = ConfigManager.get_config_section('recording_options')
    if not options.get('enable_audio_enhancement', True):
        return audio_data

    if audio_data is None or audio_data.size == 0:
        return audio_data

    original_peak = int(np.max(np.abs(audio_data)))
    audio_float = _to_float32(audio_data)

    cutoff = options.get('highpass_cutoff_hz', 80)
    if cutoff and cutoff > 0:
        audio_float = highpass_filter(audio_float, sample_rate, cutoff_hz=cutoff)

    strength = options.get('noise_reduction_strength', 0.75)
    profile_ms = options.get('noise_profile_ms', 300)
    if strength and strength > 0:
        audio_float = spectral_noise_reduce(
            audio_float,
            sample_rate,
            noise_profile_ms=profile_ms,
            strength=float(strength),
        )

    if options.get('normalize_audio', True):
        audio_float = normalize_peak(audio_float)

    result = _to_int16(audio_float)
    enhanced_peak = int(np.max(np.abs(result)))

    ConfigManager.console_print(
        f'Áudio aprimorado: pico {original_peak} → {enhanced_peak}, '
        f'passa-alta={cutoff}Hz, redução={strength:.2f}'
    )
    return result
