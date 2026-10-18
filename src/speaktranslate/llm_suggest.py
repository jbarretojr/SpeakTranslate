"""
Sugestão de resposta via IA online — Gemini (Google) ou Claude (Anthropic).

Usada pelo botão "Sugerir resposta" nas abas de tradução (ver
suggest_panel.py): a partir do texto da conversa selecionado no painel (por
padrão as falas recebidas desde a última limpeza, editável pela pessoa), pede
a um modelo uma sugestão curta de resposta no idioma de quem está falando —
pensada para quem tem domínio intermediário desse idioma e só precisa
ler/pronunciar a sugestão em voz alta, sem precisar compor a frase.

Diferente da tradução (translation.py) e da transcrição (transcription.py),
que rodam 100% localmente, isto é a única parte do app que envia o conteúdo
transcrito para um serviço externo (a API do Google ou da Anthropic) e
depende de uma chave de API. Configure GEMINI_API_KEY e/ou ANTHROPIC_API_KEY
— por exemplo, copiando ".env.example" para ".env" na raiz do projeto
(arquivo ignorado pelo git) e preenchendo a(s) chave(s) lá; elas são
carregadas automaticamente na primeira chamada, sem precisar de nenhuma
dependência extra para isso.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from env_config import load_dotenv_once

# (código, rótulo exibido na interface) — o primeiro é o padrão.
PROVIDERS = [
    ('gemini', 'Gemini'),
    ('claude', 'Claude (API)'),
    ('claude_code', 'Claude Code (assinatura)'),
]

# Onde procurar a CLI do Claude Code se ela não estiver no PATH — o app pode
# ser aberto por um atalho/IDE cujo PATH não inclui ~/.local/bin (local do
# instalador nativo, `curl -fsSL https://claude.ai/install.sh | bash`).
_CLAUDE_CODE_FALLBACK_PATHS = [
    Path.home() / '.local' / 'bin' / 'claude',
    Path('/opt/homebrew/bin/claude'),
    Path('/usr/local/bin/claude'),
]
_CLAUDE_CODE_TIMEOUT_S = 180

_GEMINI_MODEL = 'gemini-2.5-flash'
_CLAUDE_MODEL = 'claude-opus-5-5'

_gemini_client = None
_claude_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client

    load_dotenv_once()
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

    _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _get_claude_client():
    global _claude_client
    if _claude_client is not None:
        return _claude_client

    load_dotenv_once()
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError(
            'ANTHROPIC_API_KEY não configurada. Copie .env.example para .env na raiz '
            'do projeto e preencha com uma chave gerada em platform.claude.com.')

    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            'Pacote "anthropic" não instalado. Rode `poetry install` novamente '
            '(foi adicionado ao pyproject.toml).') from exc

    _claude_client = anthropic.Anthropic(api_key=api_key)
    return _claude_client


def _build_prompt(text, lang_label):
    # Sem idioma conhecido (ex.: texto digitado à mão no painel, antes de
    # qualquer fala transcrita), deixa o próprio modelo seguir o idioma da
    # mensagem.
    skill = f'domínio intermediário de {lang_label}' if lang_label else 'domínio intermediário do idioma da conversa'
    said_in = f', em {lang_label}' if lang_label else ''
    reply_in = f'em {lang_label}' if lang_label else 'no mesmo idioma da mensagem'
    return (
        f'Você está ajudando alguém com {skill} a responder, em tempo real, numa conversa '
        f'por chamada de vídeo. A outra pessoa acabou de dizer{said_in}:\n\n"{text}"\n\n'
        f'Sugira UMA resposta curta (1-2 frases), natural e educada, {reply_in}, pronta '
        f'para ser lida ou pronunciada em voz alta. Responda só com o texto da resposta, sem '
        f'aspas, sem explicações e sem oferecer opções alternativas.'
    )


def _suggest_gemini(prompt):
    client = _get_gemini_client()
    response = client.models.generate_content(model=_GEMINI_MODEL, contents=prompt)
    return response.text or ''


def _suggest_claude(prompt):
    client = _get_claude_client()
    # Esforço "low": a resposta é curta e o uso é ao vivo, então latência
    # importa mais que raciocínio profundo. O "fallbacks" faz a própria API
    # tentar outro modelo se este recusar o pedido (falso positivo dos
    # filtros de segurança), em vez de simplesmente não sugerir nada.
    response = client.beta.messages.create(
        model=_CLAUDE_MODEL,
        max_tokens=4000,
        output_config={'effort': 'low'},
        betas=['server-side-fallback-2026-07-01'],
        fallbacks='default',
        messages=[{'role': 'user', 'content': prompt}],
    )
    if response.stop_reason == 'refusal':
        raise RuntimeError('o Claude recusou gerar uma sugestão para este texto.')
    return ''.join(block.text for block in response.content if block.type == 'text')


def _find_claude_code():
    found = shutil.which('claude')
    if found:
        return found
    for path in _CLAUDE_CODE_FALLBACK_PATHS:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise RuntimeError(
        'Claude Code não encontrado. Instale com `curl -fsSL https://claude.ai/install.sh | bash` '
        'e faça login uma vez rodando `claude` no Terminal.')


def _suggest_claude_code(prompt):
    """
    Usa a CLI do Claude Code em modo não interativo (`claude -p`), com o
    login da sua assinatura (Pro/Max) — sem chave de API nem cobrança por
    uso; consome a mesma cota de uso do plano. Mais lento que a API (cada
    chamada inicia o Claude Code), o que é aceitável para um botão de uso
    esporádico.

    Uso pessoal: é você rodando o seu Claude Code localmente. Distribuir um
    app que faça outras pessoas usarem o login da assinatura delas não é
    permitido pelos termos da Anthropic — aí o caminho é a API ("Claude (API)").
    """
    claude = _find_claude_code()

    # Se ANTHROPIC_API_KEY (ou um token) estiver no ambiente — inclusive
    # vinda do .env, para o provedor "Claude (API)" —, o Claude Code passaria
    # a usá-la em vez da assinatura, e o uso seria cobrado pela API. Por
    # isso o subprocesso nunca herda essas variáveis.
    load_dotenv_once()
    env = dict(os.environ)
    for key in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN'):
        env.pop(key, None)

    # Sem ferramentas, sem servidores MCP e sem salvar a sessão: é só uma
    # geração de texto. Roda fora da pasta do projeto para não carregar o
    # CLAUDE.md/configurações dele como contexto.
    command = [claude, '-p', '--output-format', 'text', '--tools', '',
               '--strict-mcp-config', '--no-session-persistence']
    try:
        result = subprocess.run(
            command, input=prompt, capture_output=True, text=True, env=env,
            cwd=tempfile.gettempdir(), timeout=_CLAUDE_CODE_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'Claude Code não respondeu em {_CLAUDE_CODE_TIMEOUT_S}s.') from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or '').strip().splitlines()
        message = detail[-1] if detail else f'código de saída {result.returncode}'
        raise RuntimeError(
            f'Claude Code falhou ({message}). Se ainda não fez login, rode `claude` no Terminal '
            f'e use /login com a conta da sua assinatura.')
    return result.stdout


_BACKENDS = {
    'gemini': _suggest_gemini,
    'claude': _suggest_claude,
    'claude_code': _suggest_claude_code,
}


def suggest_reply(text, lang_label, provider=PROVIDERS[0][0]):
    """
    Sugere uma resposta curta e natural, no idioma `lang_label` (ex.:
    "Inglês"), para a mensagem `text` recebida nesse mesmo idioma — pronta
    para ser lida ou pronunciada em voz alta numa conversa/reunião ao vivo.

    :param provider: 'gemini', 'claude' (API) ou 'claude_code' (assinatura,
        via CLI do Claude Code) — ver PROVIDERS.

    Levanta RuntimeError com uma mensagem amigável se a chave de API não
    estiver configurada ou o pacote cliente não estiver instalado.
    """
    text = (text or '').strip()
    if not text:
        return ''
    backend = _BACKENDS.get(provider)
    if backend is None:
        raise RuntimeError(f'Provedor de IA desconhecido: {provider}')
    return backend(_build_prompt(text, lang_label)).strip()
