"""
Sugestão de resposta via Gemini (API online do Google).

Usada pelo botão "Sugerir resposta" nas abas de tradução: a partir do último
bloco transcrito/traduzido (uma sentença fechada, não o histórico acumulado),
pede a um modelo Gemini uma sugestão curta de resposta no idioma de quem está
falando — pensada para quem tem domínio intermediário desse idioma e só
precisa ler/pronunciar a sugestão em voz alta, sem precisar compor a frase.

Diferente da tradução (translation.py) e da transcrição (transcription.py),
que rodam 100% localmente, isto é a única parte do app que envia o conteúdo
transcrito para um serviço externo (a API do Google) e depende de uma chave
de API. Configure a variável de ambiente GEMINI_API_KEY para habilitar — por
exemplo, copiando ".env.example" para ".env" na raiz do projeto (arquivo
ignorado pelo git) e preenchendo a chave lá; ela é carregada automaticamente
na primeira chamada, sem precisar de nenhuma dependência extra para isso.
"""

import os
from pathlib import Path

_DEFAULT_MODEL = 'gemini-2.5-flash'

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / '.env'

_client = None
_env_loaded = False


def _load_dotenv_once():
    """Lê pares CHAVE=valor de um .env simples, sem sobrescrever variáveis já
    definidas no ambiente (ex.: exportadas no shell) e sem exigir a
    dependência python-dotenv só por causa disso."""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
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


def _get_client():
    global _client
    if _client is not None:
        return _client

    _load_dotenv_once()
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise RuntimeError(
            'GEMINI_API_KEY não configurada. Copie .env.example para .env na raiz '
            'do projeto e preencha com uma chave gerada em aistudio.google.com/apikey.')

    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            'Pacote "google-genai" não instalado. Rode `poetry install` novamente '
            '(foi adicionado ao pyproject.toml).') from exc

    _client = genai.Client(api_key=api_key)
    return _client


def suggest_reply(text, lang_label, model=_DEFAULT_MODEL):
    """
    Sugere uma resposta curta e natural, no idioma `lang_label` (ex.:
    "Inglês"), para a mensagem `text` recebida nesse mesmo idioma — pronta
    para ser lida ou pronunciada em voz alta numa conversa/reunião ao vivo.

    Levanta RuntimeError com uma mensagem amigável se a chave de API não
    estiver configurada ou o pacote cliente não estiver instalado.
    """
    text = (text or '').strip()
    if not text:
        return ''

    client = _get_client()
    prompt = (
        f'Você está ajudando alguém com domínio intermediário de {lang_label} a responder, '
        f'em tempo real, numa conversa por chamada de vídeo. A outra pessoa acabou de dizer, '
        f'em {lang_label}:\n\n"{text}"\n\n'
        f'Sugira UMA resposta curta (1-2 frases), natural e educada, em {lang_label}, pronta '
        f'para ser lida ou pronunciada em voz alta. Responda só com o texto da resposta, sem '
        f'aspas, sem explicações e sem oferecer opções alternativas.'
    )
    response = client.models.generate_content(model=model, contents=prompt)
    return (response.text or '').strip()
