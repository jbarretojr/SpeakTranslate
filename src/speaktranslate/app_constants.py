WHISPER_MODELS = ['tiny', 'base', 'small', 'medium', 'large-v3']

# Idiomas oferecidos nos comboboxes de idioma. Mantidos alinhados com as
# vozes padrão definidas em tts.py (_DEFAULT_VOICES) para garantir boa
# síntese de voz na aba "Tradução Inicial".
LANGUAGES = [
    ('pt', 'Português'),
    ('en', 'Inglês'),
    ('es', 'Espanhol'),
    ('ru', 'Russo'),
    ('fr', 'Francês'),
    ('de', 'Alemão'),
    ('it', 'Italiano'),
    ('ja', 'Japonês'),
    ('ko', 'Coreano'),
    ('zh', 'Chinês'),
]

# Motores de síntese de voz oferecidos (ver tts.py). Piper é o padrão (100%
# local/offline; baixa o modelo de voz na primeira vez que um idioma é usado,
# sem voz disponível para japonês); 'edge' é online (nuvem, vozes neurais).
# O primeiro item da lista é o selecionado por padrão na interface.
TTS_ENGINES = [
    ('piper', 'Piper (local)'),
    ('edge', 'Edge (nuvem)'),
]
