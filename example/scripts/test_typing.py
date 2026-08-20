#!/usr/bin/env python3
"""
Testa inserção de texto na janela com foco.

1. Abra o Bloco de Notas e clique dentro dele
2. Execute: poetry run python scripts/test_typing.py
3. Não mexa no mouse/teclado por 3 segundos
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import shutil
from utils import ConfigManager
from input_simulation import InputSimulator, resolve_input_method


def main():
    ConfigManager.initialize()
    configured = ConfigManager.get_config_value('post_processing', 'input_method')
    resolved = resolve_input_method(configured)

    print('=== Teste de inserção de texto ===')
    print(f'input_method (config): {configured}')
    print(f'método resolvido:       {resolved}')
    print(f'xdotool:             {shutil.which("xdotool") or "NÃO INSTALADO"}')
    print(f'xclip:               {shutil.which("xclip") or "NÃO INSTALADO"}')
    print()
    if not shutil.which('xdotool'):
        print('Instale: sudo apt install xdotool xclip')
        print('Sem xdotool, o texto NÃO será inserido em outras janelas no Linux.')
        print()
    print('Abra o Bloco de Notas, clique no texto, e aguarde...')
    for i in range(3, 0, -1):
        print(f'  {i}...')
        time.sleep(1)

    sim = InputSimulator()
    sim.typewrite('Teste VoiceNote — 1, 2, 3. Funcionou!')
    print('Comando enviado. Verifique o Bloco de Notas.')


if __name__ == '__main__':
    main()
