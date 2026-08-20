import os

import faster_whisper

assets_dir = os.path.join(os.path.dirname(faster_whisper.__file__), 'assets')
datas = [(assets_dir, 'faster_whisper/assets')]
