from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from deep_translator import MyMemoryTranslator
from deep_translator.constants import MY_MEMORY_LANGUAGES_TO_CODES

REQUEST_TIMEOUT_S = 10

# Whisper detecta idiomas em ISO-639-1 (ex.: "pt", "en"), mas o MyMemory exige
# um código de localidade completo (ex.: "pt-BR", "en-US"). Construímos um mapa
# ISO-639-1 -> localidade padrão a partir da lista de idiomas suportados pelo
# MyMemory, com preferência pelas variantes mais comuns.
_PREFERRED_LOCALES = {
    'pt': 'pt-BR',
    'en': 'en-US',
    'es': 'es-ES',
    'zh': 'zh-CN',
    'fr': 'fr-FR',
    'de': 'de-DE',
    'it': 'it-IT',
    'nl': 'nl-NL',
    'ar': 'ar-SA',
}

_ISO_TO_LOCALE = {}
for _code in MY_MEMORY_LANGUAGES_TO_CODES.values():
    _prefix = _code.split('-')[0].lower()
    _ISO_TO_LOCALE.setdefault(_prefix, _code)
_ISO_TO_LOCALE.update(_PREFERRED_LOCALES)


def _normalize(lang_code):
    if lang_code in MY_MEMORY_LANGUAGES_TO_CODES.values():
        return lang_code
    return _ISO_TO_LOCALE.get(lang_code, lang_code)


def translate(text, source_lang, target_lang, retries=1):
    """Traduz um texto do idioma de origem para o idioma de destino."""
    if not text:
        return text
    if source_lang == target_lang:
        return text

    translator = MyMemoryTranslator(source=_normalize(source_lang), target=_normalize(target_lang))

    last_error = None
    for attempt in range(retries + 1):
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(translator.translate, text)
                return future.result(timeout=REQUEST_TIMEOUT_S)
        except FutureTimeoutError as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc
    raise last_error
