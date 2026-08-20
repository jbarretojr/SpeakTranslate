from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Callable, Set

from utils import ConfigManager


class InputEvent(Enum):
    KEY_PRESS = auto()
    KEY_RELEASE = auto()
    MOUSE_PRESS = auto()
    MOUSE_RELEASE = auto()

class KeyCode(Enum):
    # Teclas modificadoras
    CTRL_LEFT = auto()
    CTRL_RIGHT = auto()
    SHIFT_LEFT = auto()
    SHIFT_RIGHT = auto()
    ALT_LEFT = auto()
    ALT_RIGHT = auto()
    META_LEFT = auto()
    META_RIGHT = auto()

    # Teclas de função
    F1 = auto()
    F2 = auto()
    F3 = auto()
    F4 = auto()
    F5 = auto()
    F6 = auto()
    F7 = auto()
    F8 = auto()
    F9 = auto()
    F10 = auto()
    F11 = auto()
    F12 = auto()
    F13 = auto()
    F14 = auto()
    F15 = auto()
    F16 = auto()
    F17 = auto()
    F18 = auto()
    F19 = auto()
    F20 = auto()
    F21 = auto()
    F22 = auto()
    F23 = auto()
    F24 = auto()

    # Teclas numéricas
    ONE = auto()
    TWO = auto()
    THREE = auto()
    FOUR = auto()
    FIVE = auto()
    SIX = auto()
    SEVEN = auto()
    EIGHT = auto()
    NINE = auto()
    ZERO = auto()

    # Teclas alfabéticas
    A = auto()
    B = auto()
    C = auto()
    D = auto()
    E = auto()
    F = auto()
    G = auto()
    H = auto()
    I = auto()
    J = auto()
    K = auto()
    L = auto()
    M = auto()
    N = auto()
    O = auto()
    P = auto()
    Q = auto()
    R = auto()
    S = auto()
    T = auto()
    U = auto()
    V = auto()
    W = auto()
    X = auto()
    Y = auto()
    Z = auto()

    # Teclas especiais
    SPACE = auto()
    ENTER = auto()
    TAB = auto()
    BACKSPACE = auto()
    ESC = auto()
    INSERT = auto()
    DELETE = auto()
    HOME = auto()
    END = auto()
    PAGE_UP = auto()
    PAGE_DOWN = auto()
    CAPS_LOCK = auto()
    NUM_LOCK = auto()
    SCROLL_LOCK = auto()
    PAUSE = auto()
    PRINT_SCREEN = auto()

    # Teclas de seta
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()

    # Teclas do teclado numérico
    NUMPAD_0 = auto()
    NUMPAD_1 = auto()
    NUMPAD_2 = auto()
    NUMPAD_3 = auto()
    NUMPAD_4 = auto()
    NUMPAD_5 = auto()
    NUMPAD_6 = auto()
    NUMPAD_7 = auto()
    NUMPAD_8 = auto()
    NUMPAD_9 = auto()
    NUMPAD_ADD = auto()
    NUMPAD_SUBTRACT = auto()
    NUMPAD_MULTIPLY = auto()
    NUMPAD_DIVIDE = auto()
    NUMPAD_DECIMAL = auto()
    NUMPAD_ENTER = auto()

    # Caracteres especiais adicionais
    MINUS = auto()
    EQUALS = auto()
    LEFT_BRACKET = auto()
    RIGHT_BRACKET = auto()
    SEMICOLON = auto()
    QUOTE = auto()
    BACKQUOTE = auto()
    BACKSLASH = auto()
    COMMA = auto()
    PERIOD = auto()
    SLASH = auto()

    # Teclas de mídia
    MUTE = auto()
    VOLUME_DOWN = auto()
    VOLUME_UP = auto()
    PLAY_PAUSE = auto()
    NEXT_TRACK = auto()
    PREV_TRACK = auto()

    # Teclas de mídia e funções especiais adicionais
    MEDIA_PLAY = auto()
    MEDIA_PAUSE = auto()
    MEDIA_PLAY_PAUSE = auto()
    MEDIA_STOP = auto()
    MEDIA_PREVIOUS = auto()
    MEDIA_NEXT = auto()
    MEDIA_REWIND = auto()
    MEDIA_FAST_FORWARD = auto()
    AUDIO_MUTE = auto()
    AUDIO_VOLUME_UP = auto()
    AUDIO_VOLUME_DOWN = auto()
    MEDIA_SELECT = auto()
    WWW = auto()
    MAIL = auto()
    CALCULATOR = auto()
    COMPUTER = auto()
    APP_SEARCH = auto()
    APP_HOME = auto()
    APP_BACK = auto()
    APP_FORWARD = auto()
    APP_STOP = auto()
    APP_REFRESH = auto()
    APP_BOOKMARKS = auto()
    BRIGHTNESS_DOWN = auto()
    BRIGHTNESS_UP = auto()
    DISPLAY_SWITCH = auto()
    KEYBOARD_ILLUMINATION_TOGGLE = auto()
    KEYBOARD_ILLUMINATION_DOWN = auto()
    KEYBOARD_ILLUMINATION_UP = auto()
    EJECT = auto()
    SLEEP = auto()
    WAKE = auto()
    EMOJI = auto()
    MENU = auto()
    CLEAR = auto()
    LOCK = auto()

    # Botões do mouse
    MOUSE_LEFT = auto()
    MOUSE_RIGHT = auto()
    MOUSE_MIDDLE = auto()
    MOUSE_BACK = auto()
    MOUSE_FORWARD = auto()
    MOUSE_SIDE1 = auto()
    MOUSE_SIDE2 = auto()
    MOUSE_SIDE3 = auto()

class InputBackend(ABC):
    """
    Classe base abstrata para backends de entrada.
    Define a interface que todos os backends de entrada devem implementar.
    """

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """
        Verifica se este backend de entrada está disponível no sistema atual.

        Retorna:
            bool: True se o backend estiver disponível, False caso contrário.
        """
        pass

    @abstractmethod
    def start(self):
        """
        Inicia o backend de entrada.
        Deve inicializar os recursos necessários e começar a escutar eventos de entrada.
        """
        pass

    @abstractmethod
    def stop(self):
        """
        Para o backend de entrada.
        Deve liberar recursos e interromper a escuta de eventos de entrada.
        """
        pass

    @abstractmethod
    def on_input_event(self, event: tuple[KeyCode, InputEvent]):
        """
        Trata um evento de entrada.
        Chamado quando um evento de entrada é detectado.

        :param event (Tuple[KeyCode, InputEvent]): tupla com o código da tecla e o tipo de evento.
        """
        pass

class KeyChord:
    """
    Representa uma combinação de teclas que precisam ser pressionadas simultaneamente.
    """

    def __init__(self, keys: Set[KeyCode | frozenset[KeyCode]]):
        """Inicializa o KeyChord."""
        self.keys = keys
        self.pressed_keys: Set[KeyCode] = set()

    def update(self, key: KeyCode, event_type: InputEvent) -> bool:
        """Atualiza o estado das teclas pressionadas e verifica se o acorde está ativo."""
        if event_type == InputEvent.KEY_PRESS:
            self.pressed_keys.add(key)
        elif event_type == InputEvent.KEY_RELEASE:
            self.pressed_keys.discard(key)

        return self.is_active()

    def is_active(self) -> bool:
        """Verifica se todas as teclas do acorde estão pressionadas."""
        for key in self.keys:
            if isinstance(key, frozenset):
                if not any(k in self.pressed_keys for k in key):
                    return False
            elif key not in self.pressed_keys:
                return False
        return True

class KeyListener:
    """
    Gerencia backends de entrada e escuta combinações específicas de teclas.
    """

    def __init__(self):
        """Inicializa o KeyListener com backends e teclas de ativação."""
        self.backends = []
        self.active_backend = None
        self.key_chord = None
        self.callbacks = {
            "on_activate": [],
            "on_deactivate": []
        }
        self.load_activation_keys()
        self.initialize_backends()
        self.select_backend_from_config()

    def initialize_backends(self):
        """Inicializa os backends de entrada disponíveis."""
        backend_classes = [EvdevBackend, PynputBackend]
        self.backends = [backend_class() for backend_class in backend_classes if backend_class.is_available()]

    def select_backend_from_config(self):
        """Seleciona o backend ativo com base na configuração."""
        preferred_backend = ConfigManager.get_config_value('recording_options', 'input_backend')

        if preferred_backend == 'auto':
            self.select_active_backend()
        else:
            backend_map = {
                'evdev': EvdevBackend,
                'pynput': PynputBackend
            }

            if preferred_backend in backend_map:
                try:
                    self.set_active_backend(backend_map[preferred_backend])
                except ValueError:
                    print(f"Backend preferido '{preferred_backend}' não está disponível. Usando seleção automática.")
                    self.select_active_backend()
            else:
                print(f"Backend desconhecido '{preferred_backend}'. Usando seleção automática.")
                self.select_active_backend()

    def select_active_backend(self):
        """Seleciona o primeiro backend disponível como ativo."""
        if not self.backends:
            raise RuntimeError(
                "Nenhum backend de teclado disponível. "
                "No Linux, tente input_backend: pynput nas configurações, "
                "ou adicione seu usuário ao grupo 'input' para usar evdev."
            )
        self.active_backend = self.backends[0]
        self.active_backend.on_input_event = self.on_input_event
        print(f"Backend de teclado: {type(self.active_backend).__name__}")

    def set_active_backend(self, backend_class):
        """Define um backend específico como ativo."""
        new_backend = next((b for b in self.backends if isinstance(b, backend_class)), None)
        if new_backend:
            if self.active_backend:
                self.stop()
            self.active_backend = new_backend
            self.active_backend.on_input_event = self.on_input_event
            self.start()
        else:
            raise ValueError(f"Backend {backend_class.__name__} não está disponível")

    def update_backend(self):
        """Atualiza o backend ativo com base na configuração atual."""
        self.select_backend_from_config()

    def start(self):
        """Inicia o backend ativo."""
        if self.active_backend:
            self.active_backend.start()
        else:
            raise RuntimeError("Nenhum backend ativo selecionado")

    def stop(self):
        """Para o backend ativo."""
        if self.active_backend:
            self.active_backend.stop()

    def load_activation_keys(self):
        """Carrega as teclas de ativação da configuração."""
        key_combination = ConfigManager.get_config_value('recording_options', 'activation_key')
        keys = self.parse_key_combination(key_combination)
        self.set_activation_keys(keys)

    def parse_key_combination(self, combination_string: str) -> Set[KeyCode | frozenset[KeyCode]]:
        """Converte uma string de combinação de teclas em um conjunto de KeyCodes."""
        keys = set()
        key_map = {
            'CTRL': frozenset({KeyCode.CTRL_LEFT, KeyCode.CTRL_RIGHT}),
            'SHIFT': frozenset({KeyCode.SHIFT_LEFT, KeyCode.SHIFT_RIGHT}),
            'ALT': frozenset({KeyCode.ALT_LEFT, KeyCode.ALT_RIGHT}),
            'META': frozenset({KeyCode.META_LEFT, KeyCode.META_RIGHT}),
        }

        for key in combination_string.upper().split('+'):
            key = key.strip()
            if key in key_map:
                keys.add(key_map[key])
            else:
                try:
                    keycode = KeyCode[key]
                    keys.add(keycode)
                except KeyError:
                    print(f"Tecla desconhecida: {key}")
        return keys

    def set_activation_keys(self, keys: Set[KeyCode]):
        """Define as teclas de ativação do KeyChord."""
        self.key_chord = KeyChord(keys)

    def on_input_event(self, event):
        """Trata eventos de entrada e dispara callbacks quando o acorde é ativado ou desativado."""
        if not self.key_chord or not self.active_backend:
            return

        key, event_type = event

        was_active = self.key_chord.is_active()
        is_active = self.key_chord.update(key, event_type)

        if not was_active and is_active:
            self._trigger_callbacks("on_activate")
        elif was_active and not is_active:
            self._trigger_callbacks("on_deactivate")

    def add_callback(self, event: str, callback: Callable):
        """Adiciona uma função de callback para um evento específico."""
        if event in self.callbacks:
            self.callbacks[event].append(callback)

    def _trigger_callbacks(self, event: str):
        """Dispara todos os callbacks associados a um evento específico."""
        for callback in self.callbacks.get(event, []):
            callback()

    def update_activation_keys(self):
        """Atualiza as teclas de ativação a partir da configuração atual."""
        self.load_activation_keys()

class EvdevBackend(InputBackend):
    """
    Backend para tratar eventos de entrada usando a biblioteca evdev.
    """

    @classmethod
    def is_available(cls) -> bool:
        """Verifica se o evdev está disponível e se os dispositivos de entrada são acessíveis."""
        try:
            import evdev
            return len(evdev.list_devices()) > 0
        except ImportError:
            return False

    def __init__(self):
        """Inicializa o EvdevBackend."""
        self.devices: List[evdev.InputDevice] = []
        self.key_map: Optional[dict] = None
        self.evdev = None
        self.thread: Optional[threading.Thread] = None
        self.stop_event: Optional[threading.Event] = None

    def start(self):
        """Inicia o backend evdev."""
        import evdev
        import threading
        self.evdev = evdev
        self.key_map = self._create_key_map()

        # Inicializa dispositivos de entrada
        self.devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        if not self.devices:
            raise RuntimeError(
                'Nenhum dispositivo de entrada acessível via evdev. '
                'Adicione seu usuário ao grupo "input" ou use input_backend: pynput.'
            )
        self.stop_event = threading.Event()
        self._setup_signal_handler()
        self._start_listening()

    def _setup_signal_handler(self):
        """Configura handlers de sinal para encerramento gracioso."""
        import signal

        def signal_handler(signum, frame):
            print("Sinal de encerramento recebido. Parando backend evdev...")
            self.stop()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    def stop(self):
        """Para o backend evdev e libera recursos."""
        if self.stop_event:
            self.stop_event.set()

        if self.thread:
            self.thread.join(timeout=1)  # aguarda até 1 segundo
            if self.thread.is_alive():
                print("Thread não encerrou a tempo. Forçando saída.")

        # Fecha todos os dispositivos
        for device in self.devices:
            try:
                device.close()
            except Exception:
                pass  # ignora erros ao fechar dispositivos
        self.devices = []

    def _start_listening(self):
        """Inicia a thread de escuta."""
        import threading
        self.thread = threading.Thread(target=self._listen_loop)
        self.thread.start()

    def _listen_loop(self):
        """Loop principal para escutar eventos de entrada."""
        import select
        while not self.stop_event.is_set():
            try:
                # Aguarda eventos de entrada com timeout de 0,1 segundos
                r, _, _ = select.select(self.devices, [], [], 0.1)
                for device in r:
                    self._read_device_events(device)
            except Exception as e:
                if self.stop_event.is_set():
                    break
                print(f"Erro inesperado em _listen_loop: {e}")

    def _read_device_events(self, device):
        """Lê e processa eventos de um único dispositivo."""
        try:
            for event in device.read():
                if event.type == self.evdev.ecodes.EV_KEY:
                    self._handle_input_event(event)
        except Exception as e:
            self._handle_device_error(device, e)

    def _handle_device_error(self, device, error):
        """Trata erros ao ler de um dispositivo."""
        import errno
        if isinstance(error, BlockingIOError) and error.errno == errno.EAGAIN:
            return  # E/S não bloqueante é esperado, apenas continua
        if isinstance(error, OSError) and (error.errno == errno.EBADF or error.errno == errno.ENODEV):
            print(f"Dispositivo {device.path} não está mais disponível. Removendo.")
            self.devices.remove(device)
        else:
            print(f"Erro inesperado ao ler dispositivo: {error}")

    def _handle_input_event(self, event):
        """Processa um único evento de entrada."""
        key_code, event_type = self._translate_key_event(event)
        if key_code is not None and event_type is not None:
            self.on_input_event((key_code, event_type))

    def _translate_key_event(self, event) -> tuple[KeyCode | None, InputEvent | None]:
        """Traduz um evento evdev para a representação interna."""
        key_event = self.evdev.categorize(event)
        if not isinstance(key_event, self.evdev.events.KeyEvent):
            return None, None

        key_code = self.key_map.get(key_event.scancode)
        if key_code is None:
            return None, None

        if key_event.keystate in [key_event.key_down, key_event.key_hold]:
            event_type = InputEvent.KEY_PRESS
        elif key_event.keystate == key_event.key_up:
            event_type = InputEvent.KEY_RELEASE
        else:
            return None, None

        return key_code, event_type

    def _create_key_map(self):
        """Cria um mapeamento dos códigos evdev para o enum KeyCode interno."""
        return {
            # Teclas modificadoras
            self.evdev.ecodes.KEY_LEFTCTRL: KeyCode.CTRL_LEFT,
            self.evdev.ecodes.KEY_RIGHTCTRL: KeyCode.CTRL_RIGHT,
            self.evdev.ecodes.KEY_LEFTSHIFT: KeyCode.SHIFT_LEFT,
            self.evdev.ecodes.KEY_RIGHTSHIFT: KeyCode.SHIFT_RIGHT,
            self.evdev.ecodes.KEY_LEFTALT: KeyCode.ALT_LEFT,
            self.evdev.ecodes.KEY_RIGHTALT: KeyCode.ALT_RIGHT,
            self.evdev.ecodes.KEY_LEFTMETA: KeyCode.META_LEFT,
            self.evdev.ecodes.KEY_RIGHTMETA: KeyCode.META_RIGHT,

            # Teclas de função
            self.evdev.ecodes.KEY_F1: KeyCode.F1,
            self.evdev.ecodes.KEY_F2: KeyCode.F2,
            self.evdev.ecodes.KEY_F3: KeyCode.F3,
            self.evdev.ecodes.KEY_F4: KeyCode.F4,
            self.evdev.ecodes.KEY_F5: KeyCode.F5,
            self.evdev.ecodes.KEY_F6: KeyCode.F6,
            self.evdev.ecodes.KEY_F7: KeyCode.F7,
            self.evdev.ecodes.KEY_F8: KeyCode.F8,
            self.evdev.ecodes.KEY_F9: KeyCode.F9,
            self.evdev.ecodes.KEY_F10: KeyCode.F10,
            self.evdev.ecodes.KEY_F11: KeyCode.F11,
            self.evdev.ecodes.KEY_F12: KeyCode.F12,

            # Teclas numéricas
            self.evdev.ecodes.KEY_1: KeyCode.ONE,
            self.evdev.ecodes.KEY_2: KeyCode.TWO,
            self.evdev.ecodes.KEY_3: KeyCode.THREE,
            self.evdev.ecodes.KEY_4: KeyCode.FOUR,
            self.evdev.ecodes.KEY_5: KeyCode.FIVE,
            self.evdev.ecodes.KEY_6: KeyCode.SIX,
            self.evdev.ecodes.KEY_7: KeyCode.SEVEN,
            self.evdev.ecodes.KEY_8: KeyCode.EIGHT,
            self.evdev.ecodes.KEY_9: KeyCode.NINE,
            self.evdev.ecodes.KEY_0: KeyCode.ZERO,

            # Teclas alfabéticas
            self.evdev.ecodes.KEY_A: KeyCode.A,
            self.evdev.ecodes.KEY_B: KeyCode.B,
            self.evdev.ecodes.KEY_C: KeyCode.C,
            self.evdev.ecodes.KEY_D: KeyCode.D,
            self.evdev.ecodes.KEY_E: KeyCode.E,
            self.evdev.ecodes.KEY_F: KeyCode.F,
            self.evdev.ecodes.KEY_G: KeyCode.G,
            self.evdev.ecodes.KEY_H: KeyCode.H,
            self.evdev.ecodes.KEY_I: KeyCode.I,
            self.evdev.ecodes.KEY_J: KeyCode.J,
            self.evdev.ecodes.KEY_K: KeyCode.K,
            self.evdev.ecodes.KEY_L: KeyCode.L,
            self.evdev.ecodes.KEY_M: KeyCode.M,
            self.evdev.ecodes.KEY_N: KeyCode.N,
            self.evdev.ecodes.KEY_O: KeyCode.O,
            self.evdev.ecodes.KEY_P: KeyCode.P,
            self.evdev.ecodes.KEY_Q: KeyCode.Q,
            self.evdev.ecodes.KEY_R: KeyCode.R,
            self.evdev.ecodes.KEY_S: KeyCode.S,
            self.evdev.ecodes.KEY_T: KeyCode.T,
            self.evdev.ecodes.KEY_U: KeyCode.U,
            self.evdev.ecodes.KEY_V: KeyCode.V,
            self.evdev.ecodes.KEY_W: KeyCode.W,
            self.evdev.ecodes.KEY_X: KeyCode.X,
            self.evdev.ecodes.KEY_Y: KeyCode.Y,
            self.evdev.ecodes.KEY_Z: KeyCode.Z,

            # Teclas especiais
            self.evdev.ecodes.KEY_SPACE: KeyCode.SPACE,
            self.evdev.ecodes.KEY_ENTER: KeyCode.ENTER,
            self.evdev.ecodes.KEY_TAB: KeyCode.TAB,
            self.evdev.ecodes.KEY_BACKSPACE: KeyCode.BACKSPACE,
            self.evdev.ecodes.KEY_ESC: KeyCode.ESC,
            self.evdev.ecodes.KEY_INSERT: KeyCode.INSERT,
            self.evdev.ecodes.KEY_DELETE: KeyCode.DELETE,
            self.evdev.ecodes.KEY_HOME: KeyCode.HOME,
            self.evdev.ecodes.KEY_END: KeyCode.END,
            self.evdev.ecodes.KEY_PAGEUP: KeyCode.PAGE_UP,
            self.evdev.ecodes.KEY_PAGEDOWN: KeyCode.PAGE_DOWN,
            self.evdev.ecodes.KEY_CAPSLOCK: KeyCode.CAPS_LOCK,
            self.evdev.ecodes.KEY_NUMLOCK: KeyCode.NUM_LOCK,
            self.evdev.ecodes.KEY_SCROLLLOCK: KeyCode.SCROLL_LOCK,
            self.evdev.ecodes.KEY_PAUSE: KeyCode.PAUSE,
            self.evdev.ecodes.KEY_SYSRQ: KeyCode.PRINT_SCREEN,

            # Teclas de seta
            self.evdev.ecodes.KEY_UP: KeyCode.UP,
            self.evdev.ecodes.KEY_DOWN: KeyCode.DOWN,
            self.evdev.ecodes.KEY_LEFT: KeyCode.LEFT,
            self.evdev.ecodes.KEY_RIGHT: KeyCode.RIGHT,

            # Teclas do teclado numérico
            self.evdev.ecodes.KEY_KP0: KeyCode.NUMPAD_0,
            self.evdev.ecodes.KEY_KP1: KeyCode.NUMPAD_1,
            self.evdev.ecodes.KEY_KP2: KeyCode.NUMPAD_2,
            self.evdev.ecodes.KEY_KP3: KeyCode.NUMPAD_3,
            self.evdev.ecodes.KEY_KP4: KeyCode.NUMPAD_4,
            self.evdev.ecodes.KEY_KP5: KeyCode.NUMPAD_5,
            self.evdev.ecodes.KEY_KP6: KeyCode.NUMPAD_6,
            self.evdev.ecodes.KEY_KP7: KeyCode.NUMPAD_7,
            self.evdev.ecodes.KEY_KP8: KeyCode.NUMPAD_8,
            self.evdev.ecodes.KEY_KP9: KeyCode.NUMPAD_9,
            self.evdev.ecodes.KEY_KPPLUS: KeyCode.NUMPAD_ADD,
            self.evdev.ecodes.KEY_KPMINUS: KeyCode.NUMPAD_SUBTRACT,
            self.evdev.ecodes.KEY_KPASTERISK: KeyCode.NUMPAD_MULTIPLY,
            self.evdev.ecodes.KEY_KPSLASH: KeyCode.NUMPAD_DIVIDE,
            self.evdev.ecodes.KEY_KPDOT: KeyCode.NUMPAD_DECIMAL,
            self.evdev.ecodes.KEY_KPENTER: KeyCode.NUMPAD_ENTER,

            # Caracteres especiais adicionais
            self.evdev.ecodes.KEY_MINUS: KeyCode.MINUS,
            self.evdev.ecodes.KEY_EQUAL: KeyCode.EQUALS,
            self.evdev.ecodes.KEY_LEFTBRACE: KeyCode.LEFT_BRACKET,
            self.evdev.ecodes.KEY_RIGHTBRACE: KeyCode.RIGHT_BRACKET,
            self.evdev.ecodes.KEY_SEMICOLON: KeyCode.SEMICOLON,
            self.evdev.ecodes.KEY_APOSTROPHE: KeyCode.QUOTE,
            self.evdev.ecodes.KEY_GRAVE: KeyCode.BACKQUOTE,
            self.evdev.ecodes.KEY_BACKSLASH: KeyCode.BACKSLASH,
            self.evdev.ecodes.KEY_COMMA: KeyCode.COMMA,
            self.evdev.ecodes.KEY_DOT: KeyCode.PERIOD,
            self.evdev.ecodes.KEY_SLASH: KeyCode.SLASH,

            # Teclas de mídia
            self.evdev.ecodes.KEY_MUTE: KeyCode.MUTE,
            self.evdev.ecodes.KEY_VOLUMEDOWN: KeyCode.VOLUME_DOWN,
            self.evdev.ecodes.KEY_VOLUMEUP: KeyCode.VOLUME_UP,
            self.evdev.ecodes.KEY_PLAYPAUSE: KeyCode.PLAY_PAUSE,
            self.evdev.ecodes.KEY_NEXTSONG: KeyCode.NEXT_TRACK,
            self.evdev.ecodes.KEY_PREVIOUSSONG: KeyCode.PREV_TRACK,

            # Teclas de função adicionais (se necessário)
            self.evdev.ecodes.KEY_F13: KeyCode.F13,
            self.evdev.ecodes.KEY_F14: KeyCode.F14,
            self.evdev.ecodes.KEY_F15: KeyCode.F15,
            self.evdev.ecodes.KEY_F16: KeyCode.F16,
            self.evdev.ecodes.KEY_F17: KeyCode.F17,
            self.evdev.ecodes.KEY_F18: KeyCode.F18,
            self.evdev.ecodes.KEY_F19: KeyCode.F19,
            self.evdev.ecodes.KEY_F20: KeyCode.F20,
            self.evdev.ecodes.KEY_F21: KeyCode.F21,
            self.evdev.ecodes.KEY_F22: KeyCode.F22,
            self.evdev.ecodes.KEY_F23: KeyCode.F23,
            self.evdev.ecodes.KEY_F24: KeyCode.F24,

            # Teclas de mídia e funções especiais adicionais
            self.evdev.ecodes.KEY_PLAYPAUSE: KeyCode.MEDIA_PLAY_PAUSE,
            self.evdev.ecodes.KEY_STOP: KeyCode.MEDIA_STOP,
            self.evdev.ecodes.KEY_PREVIOUSSONG: KeyCode.MEDIA_PREVIOUS,
            self.evdev.ecodes.KEY_NEXTSONG: KeyCode.MEDIA_NEXT,
            self.evdev.ecodes.KEY_REWIND: KeyCode.MEDIA_REWIND,
            self.evdev.ecodes.KEY_FASTFORWARD: KeyCode.MEDIA_FAST_FORWARD,
            self.evdev.ecodes.KEY_MUTE: KeyCode.AUDIO_MUTE,
            self.evdev.ecodes.KEY_VOLUMEUP: KeyCode.AUDIO_VOLUME_UP,
            self.evdev.ecodes.KEY_VOLUMEDOWN: KeyCode.AUDIO_VOLUME_DOWN,
            self.evdev.ecodes.KEY_MEDIA: KeyCode.MEDIA_SELECT,
            self.evdev.ecodes.KEY_WWW: KeyCode.WWW,
            self.evdev.ecodes.KEY_MAIL: KeyCode.MAIL,
            self.evdev.ecodes.KEY_CALC: KeyCode.CALCULATOR,
            self.evdev.ecodes.KEY_COMPUTER: KeyCode.COMPUTER,
            self.evdev.ecodes.KEY_SEARCH: KeyCode.APP_SEARCH,
            self.evdev.ecodes.KEY_HOMEPAGE: KeyCode.APP_HOME,
            self.evdev.ecodes.KEY_BACK: KeyCode.APP_BACK,
            self.evdev.ecodes.KEY_FORWARD: KeyCode.APP_FORWARD,
            self.evdev.ecodes.KEY_STOP: KeyCode.APP_STOP,
            self.evdev.ecodes.KEY_REFRESH: KeyCode.APP_REFRESH,
            self.evdev.ecodes.KEY_BOOKMARKS: KeyCode.APP_BOOKMARKS,
            self.evdev.ecodes.KEY_BRIGHTNESSDOWN: KeyCode.BRIGHTNESS_DOWN,
            self.evdev.ecodes.KEY_BRIGHTNESSUP: KeyCode.BRIGHTNESS_UP,
            self.evdev.ecodes.KEY_DISPLAYTOGGLE: KeyCode.DISPLAY_SWITCH,
            self.evdev.ecodes.KEY_KBDILLUMTOGGLE: KeyCode.KEYBOARD_ILLUMINATION_TOGGLE,
            self.evdev.ecodes.KEY_KBDILLUMDOWN: KeyCode.KEYBOARD_ILLUMINATION_DOWN,
            self.evdev.ecodes.KEY_KBDILLUMUP: KeyCode.KEYBOARD_ILLUMINATION_UP,
            self.evdev.ecodes.KEY_EJECTCD: KeyCode.EJECT,
            self.evdev.ecodes.KEY_SLEEP: KeyCode.SLEEP,
            self.evdev.ecodes.KEY_WAKEUP: KeyCode.WAKE,
            self.evdev.ecodes.KEY_COMPOSE: KeyCode.EMOJI,
            self.evdev.ecodes.KEY_MENU: KeyCode.MENU,
            self.evdev.ecodes.KEY_CLEAR: KeyCode.CLEAR,
            self.evdev.ecodes.KEY_SCREENLOCK: KeyCode.LOCK,

            # Botões do mouse
            self.evdev.ecodes.BTN_LEFT: KeyCode.MOUSE_LEFT,
            self.evdev.ecodes.BTN_RIGHT: KeyCode.MOUSE_RIGHT,
            self.evdev.ecodes.BTN_MIDDLE: KeyCode.MOUSE_MIDDLE,
            self.evdev.ecodes.BTN_SIDE: KeyCode.MOUSE_BACK,
            self.evdev.ecodes.BTN_EXTRA: KeyCode.MOUSE_FORWARD,
            self.evdev.ecodes.BTN_FORWARD: KeyCode.MOUSE_SIDE1,
            self.evdev.ecodes.BTN_BACK: KeyCode.MOUSE_SIDE2,
            self.evdev.ecodes.BTN_TASK: KeyCode.MOUSE_SIDE3,
        }

    def on_input_event(self, event):
        """
        Método de callback a ser sobrescrito pelo KeyListener.
        Chamado para cada evento de entrada processado.
        """
        pass

class PynputBackend(InputBackend):
    """
    Implementação de backend de entrada usando a biblioteca pynput.
    """

    @classmethod
    def is_available(cls) -> bool:
        """Verifica se o pynput consegue acessar o display para eventos de entrada."""
        try:
            from pynput import keyboard
            keyboard.Listener(suppress=False)
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def __init__(self):
        """Inicializa o PynputBackend."""
        self.keyboard_listener = None
        self.mouse_listener = None
        self.keyboard = None
        self.mouse = None
        self.key_map = None

    def start(self):
        """Inicia a escuta de eventos de teclado e mouse."""
        if self.keyboard is None or self.mouse is None:
            from pynput import keyboard, mouse
            self.keyboard = keyboard
            self.mouse = mouse
            self.key_map = self._create_key_map()

        self.keyboard_listener = self.keyboard.Listener(
            on_press=self._on_keyboard_press,
            on_release=self._on_keyboard_release
        )
        self.mouse_listener = self.mouse.Listener(
            on_click=self._on_mouse_click
        )
        self.keyboard_listener.start()
        self.mouse_listener.start()

    def stop(self):
        """Para a escuta de eventos de teclado e mouse."""
        if self.keyboard_listener:
            self.keyboard_listener.stop()
            self.keyboard_listener = None
        if self.mouse_listener:
            self.mouse_listener.stop()
            self.mouse_listener = None

    def _translate_key_event(self, native_event) -> tuple[KeyCode, InputEvent]:
        """Traduz um evento pynput para a representação interna de eventos."""
        pynput_key, is_press = native_event
        key_code = self.key_map.get(pynput_key, KeyCode.SPACE)
        event_type = InputEvent.KEY_PRESS if is_press else InputEvent.KEY_RELEASE
        return key_code, event_type

    def _on_keyboard_press(self, key):
        """Trata eventos de pressionamento de tecla."""
        translated_event = self._translate_key_event((key, True))
        self.on_input_event(translated_event)

    def _on_keyboard_release(self, key):
        """Trata eventos de liberação de tecla."""
        translated_event = self._translate_key_event((key, False))
        self.on_input_event(translated_event)

    def _on_mouse_click(self, x, y, button, pressed):
        """Trata eventos de clique do mouse."""
        translated_event = self._translate_key_event((button, pressed))
        self.on_input_event(translated_event)

    def _create_key_map(self):
        """Cria um mapeamento das teclas pynput para o enum KeyCode interno."""
        return {
            # Teclas modificadoras
            self.keyboard.Key.ctrl_l: KeyCode.CTRL_LEFT,
            self.keyboard.Key.ctrl_r: KeyCode.CTRL_RIGHT,
            self.keyboard.Key.shift_l: KeyCode.SHIFT_LEFT,
            self.keyboard.Key.shift_r: KeyCode.SHIFT_RIGHT,
            self.keyboard.Key.alt_l: KeyCode.ALT_LEFT,
            self.keyboard.Key.alt_r: KeyCode.ALT_RIGHT,
            self.keyboard.Key.cmd_l: KeyCode.META_LEFT,
            self.keyboard.Key.cmd_r: KeyCode.META_RIGHT,

            # Teclas de função
            self.keyboard.Key.f1: KeyCode.F1,
            self.keyboard.Key.f2: KeyCode.F2,
            self.keyboard.Key.f3: KeyCode.F3,
            self.keyboard.Key.f4: KeyCode.F4,
            self.keyboard.Key.f5: KeyCode.F5,
            self.keyboard.Key.f6: KeyCode.F6,
            self.keyboard.Key.f7: KeyCode.F7,
            self.keyboard.Key.f8: KeyCode.F8,
            self.keyboard.Key.f9: KeyCode.F9,
            self.keyboard.Key.f10: KeyCode.F10,
            self.keyboard.Key.f11: KeyCode.F11,
            self.keyboard.Key.f12: KeyCode.F12,
            self.keyboard.Key.f13: KeyCode.F13,
            self.keyboard.Key.f14: KeyCode.F14,
            self.keyboard.Key.f15: KeyCode.F15,
            self.keyboard.Key.f16: KeyCode.F16,
            self.keyboard.Key.f17: KeyCode.F17,
            self.keyboard.Key.f18: KeyCode.F18,
            self.keyboard.Key.f19: KeyCode.F19,
            self.keyboard.Key.f20: KeyCode.F20,

            # Teclas numéricas
            self.keyboard.KeyCode.from_char('1'): KeyCode.ONE,
            self.keyboard.KeyCode.from_char('2'): KeyCode.TWO,
            self.keyboard.KeyCode.from_char('3'): KeyCode.THREE,
            self.keyboard.KeyCode.from_char('4'): KeyCode.FOUR,
            self.keyboard.KeyCode.from_char('5'): KeyCode.FIVE,
            self.keyboard.KeyCode.from_char('6'): KeyCode.SIX,
            self.keyboard.KeyCode.from_char('7'): KeyCode.SEVEN,
            self.keyboard.KeyCode.from_char('8'): KeyCode.EIGHT,
            self.keyboard.KeyCode.from_char('9'): KeyCode.NINE,
            self.keyboard.KeyCode.from_char('0'): KeyCode.ZERO,

            # Teclas alfabéticas
            self.keyboard.KeyCode.from_char('a'): KeyCode.A,
            self.keyboard.KeyCode.from_char('b'): KeyCode.B,
            self.keyboard.KeyCode.from_char('c'): KeyCode.C,
            self.keyboard.KeyCode.from_char('d'): KeyCode.D,
            self.keyboard.KeyCode.from_char('e'): KeyCode.E,
            self.keyboard.KeyCode.from_char('f'): KeyCode.F,
            self.keyboard.KeyCode.from_char('g'): KeyCode.G,
            self.keyboard.KeyCode.from_char('h'): KeyCode.H,
            self.keyboard.KeyCode.from_char('i'): KeyCode.I,
            self.keyboard.KeyCode.from_char('j'): KeyCode.J,
            self.keyboard.KeyCode.from_char('k'): KeyCode.K,
            self.keyboard.KeyCode.from_char('l'): KeyCode.L,
            self.keyboard.KeyCode.from_char('m'): KeyCode.M,
            self.keyboard.KeyCode.from_char('n'): KeyCode.N,
            self.keyboard.KeyCode.from_char('o'): KeyCode.O,
            self.keyboard.KeyCode.from_char('p'): KeyCode.P,
            self.keyboard.KeyCode.from_char('q'): KeyCode.Q,
            self.keyboard.KeyCode.from_char('r'): KeyCode.R,
            self.keyboard.KeyCode.from_char('s'): KeyCode.S,
            self.keyboard.KeyCode.from_char('t'): KeyCode.T,
            self.keyboard.KeyCode.from_char('u'): KeyCode.U,
            self.keyboard.KeyCode.from_char('v'): KeyCode.V,
            self.keyboard.KeyCode.from_char('w'): KeyCode.W,
            self.keyboard.KeyCode.from_char('x'): KeyCode.X,
            self.keyboard.KeyCode.from_char('y'): KeyCode.Y,
            self.keyboard.KeyCode.from_char('z'): KeyCode.Z,

            # Teclas especiais
            self.keyboard.Key.space: KeyCode.SPACE,
            self.keyboard.Key.enter: KeyCode.ENTER,
            self.keyboard.Key.tab: KeyCode.TAB,
            self.keyboard.Key.backspace: KeyCode.BACKSPACE,
            self.keyboard.Key.esc: KeyCode.ESC,
            self.keyboard.Key.insert: KeyCode.INSERT,
            self.keyboard.Key.delete: KeyCode.DELETE,
            self.keyboard.Key.home: KeyCode.HOME,
            self.keyboard.Key.end: KeyCode.END,
            self.keyboard.Key.page_up: KeyCode.PAGE_UP,
            self.keyboard.Key.page_down: KeyCode.PAGE_DOWN,
            self.keyboard.Key.caps_lock: KeyCode.CAPS_LOCK,
            self.keyboard.Key.num_lock: KeyCode.NUM_LOCK,
            self.keyboard.Key.scroll_lock: KeyCode.SCROLL_LOCK,
            self.keyboard.Key.pause: KeyCode.PAUSE,
            self.keyboard.Key.print_screen: KeyCode.PRINT_SCREEN,

            # Teclas de seta
            self.keyboard.Key.up: KeyCode.UP,
            self.keyboard.Key.down: KeyCode.DOWN,
            self.keyboard.Key.left: KeyCode.LEFT,
            self.keyboard.Key.right: KeyCode.RIGHT,

            # Teclas do teclado numérico
            self.keyboard.Key.num_lock: KeyCode.NUM_LOCK,
            self.keyboard.KeyCode.from_vk(96): KeyCode.NUMPAD_0,
            self.keyboard.KeyCode.from_vk(97): KeyCode.NUMPAD_1,
            self.keyboard.KeyCode.from_vk(98): KeyCode.NUMPAD_2,
            self.keyboard.KeyCode.from_vk(99): KeyCode.NUMPAD_3,
            self.keyboard.KeyCode.from_vk(100): KeyCode.NUMPAD_4,
            self.keyboard.KeyCode.from_vk(101): KeyCode.NUMPAD_5,
            self.keyboard.KeyCode.from_vk(102): KeyCode.NUMPAD_6,
            self.keyboard.KeyCode.from_vk(103): KeyCode.NUMPAD_7,
            self.keyboard.KeyCode.from_vk(104): KeyCode.NUMPAD_8,
            self.keyboard.KeyCode.from_vk(105): KeyCode.NUMPAD_9,
            self.keyboard.KeyCode.from_vk(107): KeyCode.NUMPAD_ADD,
            self.keyboard.KeyCode.from_vk(109): KeyCode.NUMPAD_SUBTRACT,
            self.keyboard.KeyCode.from_vk(106): KeyCode.NUMPAD_MULTIPLY,
            self.keyboard.KeyCode.from_vk(111): KeyCode.NUMPAD_DIVIDE,
            self.keyboard.KeyCode.from_vk(110): KeyCode.NUMPAD_DECIMAL,

            # Caracteres especiais adicionais
            self.keyboard.KeyCode.from_char('-'): KeyCode.MINUS,
            self.keyboard.KeyCode.from_char('='): KeyCode.EQUALS,
            self.keyboard.KeyCode.from_char('['): KeyCode.LEFT_BRACKET,
            self.keyboard.KeyCode.from_char(']'): KeyCode.RIGHT_BRACKET,
            self.keyboard.KeyCode.from_char(';'): KeyCode.SEMICOLON,
            self.keyboard.KeyCode.from_char("'"): KeyCode.QUOTE,
            self.keyboard.KeyCode.from_char('`'): KeyCode.BACKQUOTE,
            self.keyboard.KeyCode.from_char('\\'): KeyCode.BACKSLASH,
            self.keyboard.KeyCode.from_char(','): KeyCode.COMMA,
            self.keyboard.KeyCode.from_char('.'): KeyCode.PERIOD,
            self.keyboard.KeyCode.from_char('/'): KeyCode.SLASH,

            # Teclas de mídia
            self.keyboard.Key.media_volume_mute: KeyCode.AUDIO_MUTE,
            self.keyboard.Key.media_volume_down: KeyCode.AUDIO_VOLUME_DOWN,
            self.keyboard.Key.media_volume_up: KeyCode.AUDIO_VOLUME_UP,
            self.keyboard.Key.media_play_pause: KeyCode.MEDIA_PLAY_PAUSE,
            self.keyboard.Key.media_next: KeyCode.MEDIA_NEXT,
            self.keyboard.Key.media_previous: KeyCode.MEDIA_PREVIOUS,

            # Botões do mouse
            self.mouse.Button.left: KeyCode.MOUSE_LEFT,
            self.mouse.Button.right: KeyCode.MOUSE_RIGHT,
            self.mouse.Button.middle: KeyCode.MOUSE_MIDDLE,
        }

    def on_input_event(self, event):
        """
        Método de callback definido pelo KeyListener.
        Chamado para cada evento de entrada processado.
        """
        pass
