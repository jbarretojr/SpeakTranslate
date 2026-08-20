import os
import sys

import numpy as np
import sounddevice as sd
import soundfile as sf
import yaml

# Taxas de amostragem suportadas pelo webrtcvad (usadas durante a gravação).
VAD_SAMPLE_RATES = (16000, 48000, 32000, 8000)

# Diretório raiz do projeto (junto ao executável ou raiz do fonte)
ROOT_DIR = os.environ.get(
    'VOICENOTE_ROOT',
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# Diretório dos arquivos empacotados (schema, assets internos)
if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(ROOT_DIR, 'config.yaml')
SCHEMA_PATH = os.path.join(BUNDLE_DIR, 'config_schema.yaml')
if getattr(sys, 'frozen', False):
    ASSETS_DIR = os.path.join(BUNDLE_DIR, 'assets')
else:
    ASSETS_DIR = os.path.join(ROOT_DIR, 'assets')


def supports_input_sample_rate(device, sample_rate):
    try:
        sd.check_input_settings(device=device, samplerate=sample_rate, channels=1, dtype='int16')
        return True
    except Exception:
        return False


def resolve_record_sample_rate(device, target_rate=16000):
    """
    Escolhe uma taxa de amostragem suportada pelo dispositivo de entrada.

    Prefere target_rate (16000 para Whisper). Usa outras taxas compatíveis com VAD
    como alternativa, para reamostrar depois da gravação.
    """
    if supports_input_sample_rate(device, target_rate):
        return target_rate

    for rate in VAD_SAMPLE_RATES:
        if rate != target_rate and supports_input_sample_rate(device, rate):
            return rate

    if device is None:
        device = sd.default.device[0]
    default_rate = int(sd.query_devices(device)['default_samplerate'])
    if supports_input_sample_rate(device, default_rate):
        return default_rate

    name = sd.query_devices(device)['name']
    raise ValueError(
        f'Dispositivo [{device}] "{name}" não suporta taxas compatíveis com gravação. '
        f'No Linux, use o dispositivo "pipewire" ou "default" em vez do hardware ALSA direto.'
    )


def resample_audio(audio_data, orig_sr, target_sr):
    if orig_sr == target_sr:
        return audio_data
    target_length = int(len(audio_data) * target_sr / orig_sr)
    indices = np.linspace(0, len(audio_data) - 1, target_length)
    return np.interp(indices, np.arange(len(audio_data)), audio_data.astype(np.float32)).astype(np.int16)


class ConfigManager:
    _instance = None

    def __init__(self):
        """Inicializa a instância do ConfigManager."""
        self.config = None
        self.schema = None

    @classmethod
    def initialize(cls, schema_path=None):
        """Inicializa o ConfigManager com o caminho do schema informado."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.schema = cls._instance.load_config_schema(schema_path)
            cls._instance.config = cls._instance.load_default_config()
            cls._instance.load_user_config()

    @classmethod
    def get_schema(cls):
        """Retorna o schema de configuração."""
        if cls._instance is None:
            raise RuntimeError('ConfigManager não inicializado')
        return cls._instance.schema

    @classmethod
    def get_config_section(cls, *keys):
        """Retorna uma seção específica da configuração."""
        if cls._instance is None:
            raise RuntimeError('ConfigManager não inicializado')

        section = cls._instance.config
        for key in keys:
            if isinstance(section, dict) and key in section:
                section = section[key]
            else:
                return {}
        return section

    @classmethod
    def get_config_value(cls, *keys):
        """Retorna um valor específico da configuração usando chaves aninhadas."""
        if cls._instance is None:
            raise RuntimeError('ConfigManager não inicializado')

        value = cls._instance.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    @classmethod
    def set_config_value(cls, value, *keys):
        """Define um valor específico da configuração usando chaves aninhadas."""
        if cls._instance is None:
            raise RuntimeError('ConfigManager não inicializado')

        config = cls._instance.config
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            elif not isinstance(config[key], dict):
                config[key] = {}
            config = config[key]
        config[keys[-1]] = value

    @staticmethod
    def load_config_schema(schema_path=None):
        """Carrega o schema de configuração a partir de um arquivo YAML."""
        path = schema_path or SCHEMA_PATH
        with open(path, 'r') as file:
            schema = yaml.safe_load(file)
        return schema

    def load_default_config(self):
        """Carrega os valores padrão de configuração a partir do schema."""
        def extract_value(item):
            if isinstance(item, dict):
                if 'value' in item:
                    return item['value']
                else:
                    return {k: extract_value(v) for k, v in item.items()}
            return item

        config = {}
        for category, settings in self.schema.items():
            config[category] = extract_value(settings)
        return config

    def load_user_config(self, config_path=None):
        """Carrega a configuração do usuário e mescla com a configuração padrão."""
        def deep_update(source, overrides):
            for key, value in overrides.items():
                if isinstance(value, dict) and key in source:
                    deep_update(source[key], value)
                else:
                    source[key] = value

        path = config_path or CONFIG_PATH
        if path and os.path.isfile(path):
            try:
                with open(path, 'r') as file:
                    user_config = yaml.safe_load(file)
                    deep_update(self.config, user_config)
            except yaml.YAMLError:
                print('Erro no arquivo de configuração. Usando configuração padrão.')

    @classmethod
    def save_config(cls, config_path=None):
        """Salva a configuração atual em um arquivo YAML."""
        if cls._instance is None:
            raise RuntimeError('ConfigManager não inicializado')
        path = config_path or CONFIG_PATH
        with open(path, 'w') as file:
            yaml.dump(cls._instance.config, file, default_flow_style=False)

    @classmethod
    def reload_config(cls):
        """Recarrega a configuração a partir do arquivo."""
        if cls._instance is None:
            raise RuntimeError('ConfigManager não inicializado')
        cls._instance.config = cls._instance.load_default_config()
        cls._instance.load_user_config()

    @classmethod
    def config_file_exists(cls):
        """Verifica se existe um arquivo de configuração válido."""
        return os.path.isfile(CONFIG_PATH)

    @classmethod
    def console_print(cls, message):
        """Imprime uma mensagem no terminal se habilitado na configuração."""
        if cls._instance and cls._instance.config['misc']['print_to_terminal']:
            print(message)


def play_sound(filepath):
    """Reproduz um arquivo de áudio e aguarda o término da reprodução."""
    data, samplerate = sf.read(filepath, dtype='float32')
    sd.play(data, samplerate)
    sd.wait()