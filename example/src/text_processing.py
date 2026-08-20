import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from utils import ConfigManager


BUILTIN_VOICE_COMMANDS = {
    'enter': 'enter',
    'nova linha': 'enter',
    'quebra de linha': 'enter',
    'enviar': 'enter',
    'tab': 'tab',
    'copiar': 'ctrl+c',
    'colar': 'ctrl+v',
    'desfazer': 'ctrl+z',
    'recuar': 'backspace',
    'backspace': 'backspace',
    'apagar': 'delete',
    'delete': 'delete',
    'escape': 'escape',
    'esc': 'escape',
}


@dataclass
class ProcessedTranscription:
    kind: Literal['text', 'keys', 'empty']
    text: str = ''
    keys: list | None = None


def _normalize_for_match(text):
    text = text.strip().lower()
    text = unicodedata.normalize('NFD', text)
    return ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')


def _strip_trailing_punctuation(text):
    return text.rstrip('.,!?;: ')


def _build_command_map():
    commands = dict(BUILTIN_VOICE_COMMANDS)
    custom = ConfigManager.get_config_value('text_transforms', 'custom_voice_commands') or []
    for entry in custom:
        trigger = _normalize_for_match(str(entry.get('trigger', '')))
        action = str(entry.get('action', '')).strip().lower()
        if trigger and action:
            commands[trigger] = action
    return commands


def _match_voice_command(text):
    transforms = ConfigManager.get_config_section('text_transforms')
    if not transforms.get('enable_voice_commands', True):
        return None

    normalized = _normalize_for_match(_strip_trailing_punctuation(text))
    prefix = _normalize_for_match(transforms.get('command_prefix') or 'comando')

    if not normalized.startswith(prefix):
        return None

    command_part = normalized[len(prefix):].strip()
    if not command_part:
        return None

    # Comando isolado: a transcrição inteira deve ser "prefixo + ação"
    expected = f'{prefix} {command_part}'.strip()
    if normalized != expected:
        return None

    action = _build_command_map().get(command_part)
    if not action:
        return None

    ConfigManager.console_print(f'Comando de voz detectado: {command_part} → {action}')
    return [action]


def _apply_dictionary(text, entries):
    result = text
    for entry in entries or []:
        find = str(entry.get('find', ''))
        replace = str(entry.get('replace', ''))
        if not find:
            continue
        pattern = re.compile(r'(?<!\w)' + re.escape(find) + r'(?!\w)', re.IGNORECASE)
        result = pattern.sub(replace, result)
    return result


def _apply_auto_edits(text, rules):
    result = text
    for rule in rules or []:
        find = str(rule.get('find', ''))
        replace = str(rule.get('replace', ''))
        use_regex = bool(rule.get('regex', False))
        if not find:
            continue
        try:
            if use_regex:
                result = re.sub(find, replace, result)
            else:
                result = result.replace(find, replace)
        except re.error as error:
            ConfigManager.console_print(f'Regra de edição inválida ({find!r}): {error}')
    return result


def process_transcription(text):
    """
    Processa a transcrição: comandos de voz, dicionário, edições automáticas
    e pós-processamento existente.

    Retorna ProcessedTranscription com texto para digitar ou teclas para pressionar.
    """
    if not text or not text.strip():
        return ProcessedTranscription(kind='empty')

    text = text.strip()
    keys = _match_voice_command(text)
    if keys:
        return ProcessedTranscription(kind='keys', keys=keys)

    transforms = ConfigManager.get_config_section('text_transforms')
    text = _apply_dictionary(text, transforms.get('personal_dictionary'))
    text = _apply_auto_edits(text, transforms.get('auto_edits'))

    post_processing = ConfigManager.get_config_section('post_processing')
    if post_processing.get('remove_trailing_period') and text.endswith('.'):
        text = text[:-1]
    if post_processing.get('add_trailing_space'):
        text += ' '
    if post_processing.get('remove_capitalization'):
        text = text.lower()

    if not text.strip():
        return ProcessedTranscription(kind='empty')

    return ProcessedTranscription(kind='text', text=text)
