#!/usr/bin/env python3
"""
Testa se o atalho de ativação está sendo detectado.

Uso:
    poetry run python scripts/test_hotkey.py

Pressione o atalho configurado (padrão: ctrl+shift+space).
Pressione Esc para sair.
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from utils import ConfigManager
from key_listener import KeyListener, EvdevBackend, PynputBackend


def main():
    ConfigManager.initialize()
    activation_key = ConfigManager.get_config_value('recording_options', 'activation_key')
    input_backend = ConfigManager.get_config_value('recording_options', 'input_backend')

    print('=== Teste de atalho ===')
    print(f'Atalho configurado: {activation_key}')
    print(f'input_backend:      {input_backend}')
    print(f'evdev disponível:   {EvdevBackend.is_available()}')
    print(f'pynput disponível:  {PynputBackend.is_available()}')

    if not EvdevBackend.is_available():
        print('\nNota: evdev sem dispositivos acessíveis (normal sem grupo "input").')
        print('      O app deve usar pynput automaticamente.')

    listener = KeyListener()
    backend = type(listener.active_backend).__name__
    print(f'\nBackend ativo: {backend}')
    print(f'\nPressione [{activation_key}] para testar. Ctrl+C para sair.\n')

    activated = {'count': 0}

    def on_activate():
        activated['count'] += 1
        print(f'  ✓ Atalho detectado! ({activated["count"]}x) — {time.strftime("%H:%M:%S")}')

    def on_deactivate():
        print(f'  · Atalho liberado — {time.strftime("%H:%M:%S")}')

    listener.add_callback('on_activate', on_activate)
    listener.add_callback('on_deactivate', on_deactivate)
    listener.start()

    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print('\nEncerrando...')
    finally:
        listener.stop()

    if activated['count'] == 0:
        print('\nNenhum atalho detectado.')
        print('Soluções:')
        print('  1. Em Configurações, defina input_backend como "pynput"')
        print('  2. Ou adicione seu usuário ao grupo input: sudo usermod -aG input $USER (relogin)')
        print('  3. Verifique se ctrl+shift+space não está em uso pelo sistema')
        sys.exit(1)

    print(f'\nOK — {activated["count"]} ativação(ões) detectada(s).')


if __name__ == '__main__':
    main()
