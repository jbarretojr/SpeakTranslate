"""
Leitura de um arquivo .env simples na raiz do projeto — compartilhada por
qualquer módulo que precise de uma credencial local (hoje: GEMINI_API_KEY em
llm_suggest.py, OBS_WEBSOCKET_PASSWORD em obs_controller.py/interview_gui.py).

Não sobrescreve variáveis já definidas no ambiente (ex.: exportadas no
shell) e não exige a dependência python-dotenv só por causa disso — é só
parsing de linhas "CHAVE=valor", suficiente pro caso de uso daqui. Veja
".env.example" na raiz do projeto para a lista de variáveis reconhecidas.
"""

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / '.env'

_loaded = False


def load_dotenv_once():
    """Lê pares CHAVE=valor do .env na raiz do projeto, uma única vez por
    processo. Chamar de novo depois da primeira vez não faz nada (idempotente)
    — cada módulo que precisa de uma variável pode chamar isso livremente
    antes de ler os.environ, sem se preocupar em coordenar com outros."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
