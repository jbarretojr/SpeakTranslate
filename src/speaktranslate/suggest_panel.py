import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

from app_constants import LANGUAGES
from llm_suggest import PROVIDERS, suggest_reply


class SuggestReplyPanel(ttk.Frame):
    """
    Bloco "Sugerir resposta", compartilhado pelas abas "Tradução Inicial",
    "Tradução por Streaming" e "Sugestão".

    Cada sentença fechada pela transcrição é acrescentada (via `add_block`)
    ao campo "Conversa" — o texto que será enviado à IA. O campo é editável
    e tem um botão "Limpar conversa": se foram feitas duas perguntas e você
    só quer responder a segunda, basta limpar antes dela (ou apagar a
    primeira à mão) e pedir a sugestão só com o que sobrou. A sugestão em si
    sempre SUBSTITUI a anterior (nunca acumula).

    Dois layouts (`layout`):
    - 'stacked' (padrão): compacto, empilhado abaixo da transcrição/tradução.
    - 'focus': para a aba "Sugestão" — conversa em poucas linhas com os
      botões ao lado, e a sugestão num bloco grande que ocupa o espaço que
      sobrar na tela (com rolagem e fonte maior).

    Deve ser usado só a partir da thread principal (Tkinter); a chamada à
    API roda numa thread própria e devolve o resultado por uma fila drenada
    aqui mesmo.
    """

    def __init__(self, master, layout='stacked'):
        super().__init__(master)

        self._event_queue = queue.Queue()
        self._suggesting = False
        # Idioma da fala mais recente acrescentada à conversa (código, ex.:
        # "en") — é nele que a sugestão é pedida.
        self._lang = None

        if layout == 'focus':
            self._build_focus_layout()
        else:
            self._build_stacked_layout()
        self.after(100, self._drain_queue)

    def _build_provider_combo(self, parent, width):
        self.provider_var = tk.StringVar(value=PROVIDERS[0][1])
        self.provider_combo = ttk.Combobox(
            parent, textvariable=self.provider_var, width=width, state='readonly',
            values=[label for _, label in PROVIDERS])
        return self.provider_combo

    def _build_focus_layout(self):
        top = ttk.Frame(self)
        top.pack(fill='x')
        ttk.Label(top, text='Conversa (enviada para a IA — pode editar):', foreground='#888',
                  font=('TkDefaultFont', 9)).grid(row=0, column=0, sticky='w')
        self.context_text = scrolledtext.ScrolledText(
            top, height=4, wrap='word', padx=8, pady=6, font=('TkDefaultFont', 12))
        self.context_text.grid(row=1, column=0, sticky='nsew', pady=(2, 0))

        side = ttk.Frame(top)
        side.grid(row=1, column=1, sticky='n', padx=(8, 0), pady=(2, 0))
        self.suggest_button = ttk.Button(side, text='💡 Sugerir resposta', command=self._on_suggest_click)
        self.suggest_button.pack(fill='x')
        self.clear_button = ttk.Button(side, text='🧹 Limpar conversa', command=self.clear)
        self.clear_button.pack(fill='x', pady=(4, 0))
        ttk.Label(side, text='IA:', foreground='#888', font=('TkDefaultFont', 9)).pack(anchor='w', pady=(6, 0))
        self._build_provider_combo(side, width=20).pack(fill='x')
        top.columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value='')
        ttk.Label(self, textvariable=self.status_var, foreground='#888').pack(anchor='w', pady=(4, 0))

        ttk.Label(self, text='Sugestão', font=('TkDefaultFont', 11, 'bold')).pack(anchor='w', pady=(4, 0))
        # height pequeno só define o tamanho MÍNIMO pedido; com expand=True o
        # bloco cresce para ocupar todo o espaço livre da janela.
        self.suggest_text = scrolledtext.ScrolledText(
            self, height=6, state='disabled', wrap='word', padx=14, pady=12, font=('TkDefaultFont', 17))
        self.suggest_text.pack(fill='both', expand=True, pady=(2, 0))

    def _build_stacked_layout(self):
        row = ttk.Frame(self)
        row.pack(fill='x')

        self.suggest_button = ttk.Button(row, text='💡 Sugerir resposta', command=self._on_suggest_click)
        self.suggest_button.pack(side='left')
        self.clear_button = ttk.Button(row, text='🧹 Limpar conversa', command=self.clear)
        self.clear_button.pack(side='left', padx=(6, 0))

        ttk.Label(row, text='IA:').pack(side='left', padx=(14, 0))
        self._build_provider_combo(row, width=22).pack(side='left', padx=(4, 0))

        self.status_var = tk.StringVar(value='')
        ttk.Label(row, textvariable=self.status_var, foreground='#888').pack(side='left', padx=(10, 0))

        ttk.Label(self, text='Conversa (enviada para a sugestão — pode editar):', foreground='#888',
                  font=('TkDefaultFont', 9)).pack(anchor='w', pady=(6, 0))
        self.context_text = tk.Text(self, height=3, wrap='word', padx=10, pady=6)
        self.context_text.pack(fill='x', pady=(2, 0))

        ttk.Label(self, text='Sugestão:', foreground='#888',
                  font=('TkDefaultFont', 9)).pack(anchor='w', pady=(6, 0))
        self.suggest_text = tk.Text(self, height=3, state='disabled', wrap='word', padx=10, pady=6)
        self.suggest_text.pack(fill='x', pady=(2, 0))

    def add_block(self, text, lang):
        """Acrescenta uma sentença fechada (no idioma original) à conversa."""
        text = (text or '').strip()
        if not text:
            return
        existing = self.context_text.get('1.0', 'end-1c')
        separator = ' ' if existing and not existing.endswith((' ', '\n')) else ''
        self.context_text.insert('end', separator + text)
        self.context_text.see('end')
        if lang:
            self._lang = lang

    def clear(self):
        """Apaga a conversa acumulada; a próxima fala começa um contexto novo."""
        self.context_text.delete('1.0', 'end')
        self.status_var.set('')

    def _selected_provider(self):
        label = self.provider_var.get()
        return next((code for code, provider_label in PROVIDERS if provider_label == label), PROVIDERS[0][0])

    def _on_suggest_click(self):
        if self._suggesting:
            return
        text = self.context_text.get('1.0', 'end-1c').strip()
        if not text:
            self.status_var.set('Nenhuma conversa para sugerir uma resposta.')
            return

        lang_label = next((label for code, label in LANGUAGES if code == self._lang), self._lang or '')

        self._suggesting = True
        self.suggest_button.configure(state='disabled')
        self.status_var.set('Gerando sugestão...')
        threading.Thread(target=self._suggest_worker, args=(text, lang_label, self._selected_provider()),
                         daemon=True).start()

    def _suggest_worker(self, text, lang_label, provider):
        try:
            suggestion = suggest_reply(text, lang_label, provider=provider)
            self._event_queue.put(('suggestion', suggestion or '(sem sugestão)'))
            self._event_queue.put(('status', ''))
        except Exception as exc:
            self._event_queue.put(('status', f'Erro: {exc}'))
        finally:
            self._event_queue.put(('done', None))

    def _drain_queue(self):
        while True:
            try:
                kind, payload = self._event_queue.get_nowait()
            except queue.Empty:
                break

            if kind == 'suggestion':
                self.suggest_text.configure(state='normal')
                self.suggest_text.delete('1.0', 'end')
                self.suggest_text.insert('end', payload)
                self.suggest_text.configure(state='disabled')
            elif kind == 'status':
                self.status_var.set(payload)
            elif kind == 'done':
                self._suggesting = False
                self.suggest_button.configure(state='normal')

        self.after(100, self._drain_queue)
