import os
import sys
from dotenv import load_dotenv

# Detecta se está rodando como executável PyInstaller
if getattr(sys, 'frozen', False):
    ROOT = os.path.dirname(sys.executable)
    MEIPASS = sys._MEIPASS
else:
    ROOT = os.path.dirname(os.path.abspath(__file__))
    MEIPASS = ROOT

sys.path.insert(0, os.path.join(MEIPASS, 'src'))

# Expõe o ROOT para os demais módulos resolverem assets/config
os.environ['VOICENOTE_ROOT'] = ROOT

from system_deps import ensure_system_dependencies

print('Iniciando VoiceNote...')
load_dotenv()

if not ensure_system_dependencies():
    print('Aviso: algumas dependências de sistema não estão disponíveis.')
    print('O aplicativo pode não inserir texto em outras janelas.')

import main
app = main.VoiceNoteApp()
app.run()