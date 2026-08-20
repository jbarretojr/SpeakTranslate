import os
import shutil
import signal
import subprocess
import time

import pyperclip
from pynput.keyboard import Controller as PynputController, Key

from utils import ConfigManager


XDOTOOL_KEY_MAP = {
    'enter': 'Return',
    'return': 'Return',
    'tab': 'Tab',
    'backspace': 'BackSpace',
    'delete': 'Delete',
    'escape': 'Escape',
    'esc': 'Escape',
    'space': 'space',
    'up': 'Up',
    'down': 'Down',
    'left': 'Left',
    'right': 'Right',
    'home': 'Home',
    'end': 'End',
    'pageup': 'Page_Up',
    'pagedown': 'Page_Down',
}

PYNPUT_KEY_MAP = {
    'enter': Key.enter,
    'return': Key.enter,
    'tab': Key.tab,
    'backspace': Key.backspace,
    'delete': Key.delete,
    'escape': Key.esc,
    'esc': Key.esc,
    'space': Key.space,
    'up': Key.up,
    'down': Key.down,
    'left': Key.left,
    'right': Key.right,
    'home': Key.home,
    'end': Key.end,
    'pageup': Key.page_up,
    'pagedown': Key.page_down,
}

PYNPUT_MODIFIER_MAP = {
    'ctrl': Key.ctrl,
    'control': Key.ctrl,
    'shift': Key.shift,
    'alt': Key.alt,
    'meta': Key.cmd,
    'super': Key.cmd,
    'win': Key.cmd,
}


def _tool_available(name):
    return shutil.which(name) is not None


def resolve_input_method(configured):
    """Escolhe o melhor método de entrada disponível neste sistema."""
    if configured != 'auto':
        return configured

    if _tool_available('xdotool'):
        return 'clipboard'
    if _tool_available('ydotool'):
        return 'ydotool'
    return 'pynput'


class InputSimulator:
    """Simula entrada de teclado usando vários métodos."""

    def __init__(self):
        configured = ConfigManager.get_config_value('post_processing', 'input_method')
        self.input_method = resolve_input_method(configured)
        self.dotool_process = None
        self.keyboard = PynputController()

        if configured == 'auto':
            ConfigManager.console_print(f'input_method auto → {self.input_method}')

        if self.input_method == 'dotool':
            self._initialize_dotool()

    def _initialize_dotool(self):
        self.dotool_process = subprocess.Popen("dotool", stdin=subprocess.PIPE, text=True)
        assert self.dotool_process.stdin is not None

    def _terminate_dotool(self):
        if self.dotool_process:
            os.kill(self.dotool_process.pid, signal.SIGINT)
            self.dotool_process = None

    def _run(self, command, check=True):
        subprocess.run(command, check=check, env=os.environ.copy())

    def typewrite(self, text):
        if not text or not text.strip():
            return

        ConfigManager.console_print(f'Inserindo texto ({self.input_method}): {text!r}')
        interval = ConfigManager.get_config_value('post_processing', 'writing_key_press_delay')
        time.sleep(0.15)

        if self.input_method == 'clipboard':
            self._typewrite_clipboard(text)
        elif self.input_method == 'pynput':
            self._typewrite_pynput(text, interval)
        elif self.input_method == 'ydotool':
            self._typewrite_ydotool(text, interval)
        elif self.input_method == 'dotool':
            self._typewrite_dotool(text, interval)
        elif self.input_method == 'xdotool':
            self._typewrite_xdotool(text, interval)
        else:
            ConfigManager.console_print(f'Método de input desconhecido: {self.input_method}')
            self._typewrite_clipboard(text)

    def press_keys(self, key_specs):
        """Pressiona uma ou mais combinações de teclas (ex.: 'enter', 'ctrl+c')."""
        if not key_specs:
            return

        ConfigManager.console_print(f'Executando teclas ({self.input_method}): {key_specs}')
        time.sleep(0.15)

        for spec in key_specs:
            self._press_key_spec(spec)

    def _press_key_spec(self, spec):
        spec = spec.strip().lower()
        if not spec:
            return

        if self.input_method in ('clipboard', 'xdotool') and _tool_available('xdotool'):
            self._press_xdotool(spec)
        elif self.input_method == 'ydotool' and _tool_available('ydotool'):
            self._press_ydotool(spec)
        elif self.input_method == 'dotool' and self.dotool_process:
            self._press_dotool(spec)
        else:
            self._press_pynput(spec)

    def _press_xdotool(self, spec):
        key_token = self._to_xdotool_key(spec)
        self._run(['xdotool', 'key', '--clearmodifiers', key_token])

    def _to_xdotool_key(self, spec):
        if '+' in spec:
            parts = [part.strip() for part in spec.split('+')]
            mapped = []
            for part in parts:
                if part in ('ctrl', 'control', 'shift', 'alt', 'meta', 'super'):
                    mapped.append(part if part != 'control' else 'ctrl')
                else:
                    mapped.append(XDOTOOL_KEY_MAP.get(part, part))
            return '+'.join(mapped)
        return XDOTOOL_KEY_MAP.get(spec, spec)

    def _press_ydotool(self, spec):
        # ydotool usa códigos; para combinações comuns, delegamos ao xdotool se disponível
        if _tool_available('xdotool'):
            self._press_xdotool(spec)
            return
        self._press_pynput(spec)

    def _press_dotool(self, spec):
        assert self.dotool_process and self.dotool_process.stdin
        if '+' in spec:
            parts = [part.strip() for part in spec.split('+')]
            for part in parts[:-1]:
                self.dotool_process.stdin.write(f"keydown {part}\n")
            self.dotool_process.stdin.write(f"key {parts[-1]}\n")
            for part in reversed(parts[:-1]):
                self.dotool_process.stdin.write(f"keyup {part}\n")
        else:
            self.dotool_process.stdin.write(f"key {spec}\n")
        self.dotool_process.stdin.flush()

    def _press_pynput(self, spec):
        if '+' in spec:
            parts = [part.strip() for part in spec.split('+')]
            modifiers = [PYNPUT_MODIFIER_MAP[part] for part in parts[:-1]]
            key_name = parts[-1]
            key = PYNPUT_KEY_MAP.get(key_name, key_name)
            with self.keyboard.pressed(*modifiers):
                if isinstance(key, Key):
                    self.keyboard.press(key)
                    self.keyboard.release(key)
                else:
                    self.keyboard.press(key)
                    self.keyboard.release(key)
            return

        key = PYNPUT_KEY_MAP.get(spec, spec)
        if isinstance(key, Key):
            self.keyboard.press(key)
            self.keyboard.release(key)
        else:
            self.keyboard.press(key)
            self.keyboard.release(key)

    def _typewrite_clipboard(self, text):
        """Copia para a área de transferência e cola na janela em foco."""
        pyperclip.copy(text)
        time.sleep(0.05)

        if _tool_available('xdotool'):
            self._run(['xdotool', 'key', '--clearmodifiers', 'ctrl+v'])
            return

        if _tool_available('ydotool'):
            self._run(['ydotool', 'key', '29:1', '47:1', '47:0', '29:0'])  # ctrl+v
            return

        ConfigManager.console_print(
            'AVISO: instale xdotool para colar em outros apps: sudo apt install xdotool xclip'
        )
        with self.keyboard.pressed(Key.ctrl):
            self.keyboard.press('v')
            self.keyboard.release('v')

    def _typewrite_pynput(self, text, interval):
        if interval:
            for char in text:
                self.keyboard.type(char)
                time.sleep(interval)
        else:
            self.keyboard.type(text)

    def _typewrite_xdotool(self, text, interval):
        self._run([
            'xdotool', 'type', '--clearmodifiers',
            '--delay', str(int(interval * 1000)),
            '--', text,
        ])

    def _typewrite_ydotool(self, text, interval):
        self._run([
            'ydotool', 'type',
            '--key-delay', str(int(interval * 1000)),
            '--', text,
        ])

    def _typewrite_dotool(self, text, interval):
        assert self.dotool_process and self.dotool_process.stdin
        self.dotool_process.stdin.write(f"typedelay {interval * 1000}\n")
        self.dotool_process.stdin.write(f"type {text}\n")
        self.dotool_process.stdin.flush()

    def cleanup(self):
        if self.input_method == 'dotool':
            self._terminate_dotool()
