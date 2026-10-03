"""
Detecção do idioma de um texto digitado (não áudio) — usada pela aba
"Microfone Virtual" para decidir se precisa traduzir antes de falar: se o
texto já estiver no idioma de saída escolhido, fala direto; se estiver em
outro idioma, traduz primeiro (ver translation.py) e fala o resultado.

Usa py3langid (fork mantido do langid.py), 100% local/offline: nenhum texto
é enviado para fora, só um classificador estatístico (treinado previamente)
roda em memória — sem relação com a detecção de idioma do Whisper usada nas
outras abas, que trabalha em cima do áudio, não do texto.
"""

import py3langid as langid

from app_constants import LANGUAGES

# Restringe o classificador aos idiomas que o app realmente oferece — além
# de mais rápido, melhora a precisão (ele é forçado a escolher entre essas
# opções em vez de qualquer um dos ~97 idiomas que conhece).
langid.set_languages([code for code, _ in LANGUAGES])


def detect_language(text):
    """
    Detecta o idioma de `text`, restrito aos idiomas de app_constants.LANGUAGES.

    :return: código do idioma (ex.: 'en', 'pt'), ou None se `text` for vazio.
        Textos muito curtos (ex.: uma palavra só) são mais propensos a
        detecção errada — limitação inerente a esse tipo de classificador,
        não há como eliminar totalmente.
    """
    text = (text or '').strip()
    if not text:
        return None
    lang_code, _score = langid.classify(text)
    return lang_code
