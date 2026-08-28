"""
Tradução local, offline, usando modelos OPUS-MT (Helsinki-NLP) rodando via
CTranslate2 — o mesmo motor que já usamos para o Whisper (faster-whisper).

Por que local em vez de um serviço online: mais rápido (~60-150ms por frase
aqui vs. ~1,5-3,5s de round-trip para o MyMemory nos nossos testes), sem
depender de internet nem de limites de requisições de um serviço gratuito, e
sem enviar o conteúdo transcrito para terceiros.

Cada par de idioma "direto" (envolvendo inglês) usa um modelo OPUS-MT
específico. Pares que não envolvem inglês são traduzidos em duas etapas via
inglês como pivô (ex.: espanhol -> russo vira espanhol -> inglês -> russo) —
prática padrão quando não existe um modelo bilíngue direto para o par.

Os modelos são baixados e convertidos para o formato CTranslate2 (int8) na
primeira vez que um par de idiomas é usado, e então ficam em cache em
~/.cache/speaktranslate/ct2_models/ — chamadas seguintes são 100% locais.
"""

import re
from pathlib import Path

import ctranslate2

# Modelos OPUS-MT são treinados para tradução por frase; um texto com várias
# frases enviado de uma vez pode ter conteúdo descartado ou resumido. Por
# isso dividimos o texto em frases e traduzimos cada uma separadamente.
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?…])\s+')

CACHE_DIR = Path.home() / '.cache' / 'speaktranslate' / 'ct2_models'

# Par (origem, destino) -> repositório HuggingFace do modelo OPUS-MT
# correspondente. Só cobrimos pares que envolvem inglês; qualquer outro par
# é resolvido em duas etapas via inglês (ver `_route`).
_DIRECT_MODELS = {
    ('es', 'en'): 'Helsinki-NLP/opus-mt-es-en',
    ('en', 'es'): 'Helsinki-NLP/opus-mt-en-es',
    ('fr', 'en'): 'Helsinki-NLP/opus-mt-fr-en',
    ('en', 'fr'): 'Helsinki-NLP/opus-mt-en-fr',
    ('de', 'en'): 'Helsinki-NLP/opus-mt-de-en',
    ('en', 'de'): 'Helsinki-NLP/opus-mt-en-de',
    ('it', 'en'): 'Helsinki-NLP/opus-mt-it-en',
    ('en', 'it'): 'Helsinki-NLP/opus-mt-en-it',
    ('ru', 'en'): 'Helsinki-NLP/opus-mt-ru-en',
    ('en', 'ru'): 'Helsinki-NLP/opus-mt-en-ru',
    ('zh', 'en'): 'Helsinki-NLP/opus-mt-zh-en',
    ('en', 'zh'): 'Helsinki-NLP/opus-mt-en-zh',
    ('ja', 'en'): 'Helsinki-NLP/opus-mt-ja-en',
    ('en', 'ja'): 'Helsinki-NLP/opus-mt-en-jap',
    ('ko', 'en'): 'Helsinki-NLP/opus-mt-tc-big-ko-en',
    ('en', 'ko'): 'Helsinki-NLP/opus-mt-tc-big-en-ko',
    # Não existe um modelo pt<->en dedicado no OPUS-MT; pt->en usa o modelo
    # multi-origem "ROMANCE" (treinado com vários idiomas latinos, incluindo
    # português, como origem) e en->pt usa a variante "tc-big" (maior/melhor).
    ('pt', 'en'): 'Helsinki-NLP/opus-mt-ROMANCE-en',
    ('en', 'pt'): 'Helsinki-NLP/opus-mt-tc-big-en-pt',
}

_engines = {}  # repo_id -> (ctranslate2.Translator, tokenizer)


def _route(source_lang, target_lang):
    """Retorna a lista de pares (origem, destino) a traduzir em sequência."""
    if (source_lang, target_lang) in _DIRECT_MODELS:
        return [(source_lang, target_lang)]
    if source_lang != 'en' and target_lang != 'en':
        return [(source_lang, 'en'), ('en', target_lang)]
    raise ValueError(f'Par de idiomas não suportado para tradução local: {source_lang} -> {target_lang}')


def _local_model_dir(repo_id):
    return CACHE_DIR / repo_id.replace('/', '__')


def _load_engine(repo_id):
    if repo_id in _engines:
        return _engines[repo_id]

    # Import tardio: transformers/torch só são necessários na primeira vez
    # que um par de idiomas é usado (conversão HF -> CTranslate2); depois
    # disso, só ctranslate2 é necessário para traduzir.
    from transformers import AutoTokenizer

    model_dir = _local_model_dir(repo_id)
    if not (model_dir / 'model.bin').exists():
        from ctranslate2.converters import TransformersConverter
        model_dir.parent.mkdir(parents=True, exist_ok=True)
        TransformersConverter(repo_id).convert(str(model_dir), quantization='int8', force=True)

    tokenizer = AutoTokenizer.from_pretrained(repo_id)
    translator = ctranslate2.Translator(str(model_dir), device='cpu')
    _engines[repo_id] = (translator, tokenizer)
    return _engines[repo_id]


def _translate_direct(text, repo_id):
    translator, tokenizer = _load_engine(repo_id)
    source_tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(text))
    result = translator.translate_batch([source_tokens])
    output_tokens = result[0].hypotheses[0]
    return tokenizer.decode(tokenizer.convert_tokens_to_ids(output_tokens), skip_special_tokens=True)


def _translate_sentence(text, hops, retries):
    last_error = None
    for attempt in range(retries + 1):
        try:
            result = text
            for hop_source, hop_target in hops:
                result = _translate_direct(result, _DIRECT_MODELS[(hop_source, hop_target)])
            return result
        except Exception as exc:
            last_error = exc
    raise last_error


def translate(text, source_lang, target_lang, retries=1):
    """Traduz um texto do idioma de origem para o idioma de destino (local, offline)."""
    if not text:
        return text
    if source_lang == target_lang:
        return text

    hops = _route(source_lang, target_lang)

    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s]
    if len(sentences) <= 1:
        return _translate_sentence(text, hops, retries)

    return ' '.join(_translate_sentence(sentence, hops, retries) for sentence in sentences)
