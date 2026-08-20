from deep_translator import GoogleTranslator

# Whisper detecta "pt" para português; o Google Translate distingue pt/pt-BR,
# mas aceita "pt" tanto como origem quanto como destino.
_LANG_ALIASES = {
    'zh': 'zh-CN',
}


def _normalize(lang_code):
    return _LANG_ALIASES.get(lang_code, lang_code)


def translate(text, source_lang, target_lang):
    """Traduz um texto do idioma de origem para o idioma de destino."""
    if not text:
        return text
    if source_lang == target_lang:
        return text

    translator = GoogleTranslator(source=_normalize(source_lang), target=_normalize(target_lang))
    return translator.translate(text)
