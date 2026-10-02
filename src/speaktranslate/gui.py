import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

from app_constants import LANGUAGES, TTS_ENGINES, WHISPER_MODELS
from audio_capture import list_input_devices, record_utterance
from llm_suggest import suggest_reply
from streaming_gui import StreamingTranslationTab
from transcription import create_model, transcribe
from translation import translate
from tts import speak
from virtual_mic_gui import VirtualMicTab

SAMPLE_RATE = 16000
DEFAULT_MODEL = 'base'
DEFAULT_TARGET_LANG = 'pt'

# Rótulos do botão de alternância, no mesmo espírito do atalho
# Ctrl+Shift+Space do VoiceNote: um clique inicia a gravação, o próximo
# apenas sinaliza "parar de gravar agora" — a partir daí transcrição,
# tradução e fala rodam até o fim sem chance de serem interrompidas no meio.
LABEL_IDLE = '🎙 Iniciar Transcrição'
LABEL_RECORDING = '⏹ Parar Transcrição'
LABEL_PROCESSING = 'Processando...'


class InitialTranslationTab(ttk.Frame):
    """
    Aba "Tradução Inicial": grava uma fala por vez (toggle iniciar/parar
    gravação), transcreve, traduz e fala o resultado. Mesmo visual da aba
    "Tradução por Streaming" (configuração compacta no topo, transcrição e
    tradução lado a lado em destaque) e o mesmo botão "Sugerir resposta"
    (ver llm_suggest.py) — cada gravação é o seu próprio "bloco": a sugestão
    sempre se refere à última fala capturada, nunca acumula com as
    anteriores.
    """

    def __init__(self, master):
        super().__init__(master, padding=0)

        self.model = None
        self._loaded_model_size = None

        # Tkinter não é thread-safe: chamar métodos de widgets (inclusive
        # `after`) a partir da worker thread não é confiável e pode
        # simplesmente nunca disparar. Por isso toda comunicação da worker
        # thread com a UI passa por esta fila, drenada por um polling que
        # roda inteiramente na thread principal (_drain_queue).
        self._event_queue = queue.Queue()

        # 'idle' | 'recording' | 'processing'
        self._state = 'idle'
        self._record_stop_event = threading.Event()
        self._worker_thread = None
        self._input_devices = []

        # Última fala capturada (texto original + idioma detectado) — usada
        # pelo botão "Sugerir resposta"; nunca acumula entre gravações.
        self._last_block_text = ''
        self._last_block_lang = None
        self._suggesting = False

        self._build_widgets()
        self._refresh_devices()
        self.after(100, self._drain_queue)

    def _build_widgets(self):
        self._build_options_bar()
        self._build_control_row()
        self._build_main_panes()
        self._build_suggest_block()

    def _build_options_bar(self):
        """Barra compacta de configuração, no mesmo estilo da aba de
        streaming: rótulos curtos, widgets lado a lado."""
        frame = ttk.Frame(self, padding=(10, 8, 10, 4))
        frame.pack(fill='x')

        ttk.Label(frame, text='Destino:').grid(row=0, column=0, sticky='w')
        default_label = next(
            (label for code, label in LANGUAGES if code == DEFAULT_TARGET_LANG), LANGUAGES[0][1])
        self.target_lang_var = tk.StringVar(value=default_label)
        self.target_lang_entry = ttk.Combobox(
            frame, textvariable=self.target_lang_var, width=12, state='readonly',
            values=[label for _, label in LANGUAGES])
        self.target_lang_entry.grid(row=0, column=1, sticky='w', padx=(4, 14))

        ttk.Label(frame, text='Modelo:').grid(row=0, column=2, sticky='w')
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.model_combo = ttk.Combobox(frame, textvariable=self.model_var, width=8,
                                         values=WHISPER_MODELS, state='readonly')
        self.model_combo.grid(row=0, column=3, sticky='w', padx=(4, 14))

        ttk.Label(frame, text='Voz:').grid(row=0, column=4, sticky='w')
        default_tts_label = TTS_ENGINES[0][1]
        self.tts_engine_var = tk.StringVar(value=default_tts_label)
        self.tts_engine_combo = ttk.Combobox(
            frame, textvariable=self.tts_engine_var, width=12, state='readonly',
            values=[label for _, label in TTS_ENGINES])
        self.tts_engine_combo.grid(row=0, column=5, sticky='w', padx=4)

        ttk.Label(frame, text='Entrada:').grid(row=1, column=0, sticky='w', pady=(6, 0))
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(frame, textvariable=self.device_var, width=32, state='readonly')
        self.device_combo.grid(row=1, column=1, columnspan=3, sticky='we', padx=(4, 4), pady=(6, 0))
        self.refresh_devices_button = ttk.Button(frame, text='⟳', width=3, command=self._refresh_devices)
        self.refresh_devices_button.grid(row=1, column=4, sticky='w', pady=(6, 0))

        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

    def _build_control_row(self):
        frame = ttk.Frame(self, padding=(10, 4, 10, 4))
        frame.pack(fill='x')
        self.toggle_button = ttk.Button(frame, text=LABEL_IDLE, command=self._on_toggle)
        self.toggle_button.pack(side='left')
        self.status_var = tk.StringVar(value='')
        ttk.Label(frame, textvariable=self.status_var, font=('TkDefaultFont', 11, 'bold')).pack(
            side='left', padx=(10, 0))

    def _build_main_panes(self):
        """Transcrição e tradução lado a lado, em destaque — mesmo layout da
        aba de streaming."""
        panes = ttk.Panedwindow(self, orient='horizontal')
        panes.pack(fill='both', expand=True, padx=10, pady=(4, 8))

        transcript_frame = ttk.Frame(panes)
        ttk.Label(transcript_frame, text='Transcrição (original)',
                  font=('TkDefaultFont', 11, 'bold')).pack(anchor='w')
        self.transcript_text = scrolledtext.ScrolledText(
            transcript_frame, height=16, state='disabled', wrap='word', font=('TkDefaultFont', 12))
        self.transcript_text.pack(fill='both', expand=True, pady=(4, 0))
        panes.add(transcript_frame, weight=1)

        translation_frame = ttk.Frame(panes)
        ttk.Label(translation_frame, text='Tradução', font=('TkDefaultFont', 11, 'bold')).pack(anchor='w')
        self.translation_text = scrolledtext.ScrolledText(
            translation_frame, height=16, state='disabled', wrap='word', font=('TkDefaultFont', 12))
        self.translation_text.pack(fill='both', expand=True, pady=(4, 0))
        panes.add(translation_frame, weight=1)

    def _build_suggest_block(self):
        """Botão "Sugerir resposta": mesmo mecanismo da aba de streaming (ver
        llm_suggest.py), aplicado à última gravação transcrita."""
        frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        frame.pack(fill='x')

        self.suggest_button = ttk.Button(
            frame, text='💡 Sugerir resposta', command=self._on_suggest_click)
        self.suggest_button.pack(side='left')
        self.suggest_status_var = tk.StringVar(value='')
        ttk.Label(frame, textvariable=self.suggest_status_var, foreground='#888').pack(
            side='left', padx=(10, 0))

        self.suggest_text = tk.Text(self, height=3, state='disabled', wrap='word', padx=10, pady=6)
        self.suggest_text.pack(fill='x', padx=10, pady=(0, 10))

    def _refresh_devices(self):
        previous = self.device_var.get()
        devices = list_input_devices()
        self._input_devices = [
            (i, d['name']) for i, d in enumerate(devices) if d.get('max_input_channels', 0) > 0
        ]
        labels = [f'{i}: {name}' for i, name in self._input_devices]
        self.device_combo.configure(values=labels)
        if previous in labels:
            self.device_var.set(previous)
        elif labels:
            self.device_var.set(labels[0])
        else:
            self.device_var.set('')

    def _selected_device_index(self):
        label = self.device_var.get()
        if not label:
            return None
        return int(label.split(':', 1)[0])

    def _selected_target_lang_code(self):
        label = self.target_lang_var.get()
        for code, lang_label in LANGUAGES:
            if lang_label == label:
                return code
        return DEFAULT_TARGET_LANG

    def _selected_tts_engine(self):
        label = self.tts_engine_var.get()
        for code, engine_label in TTS_ENGINES:
            if engine_label == label:
                return code
        return TTS_ENGINES[0][0]

    # -- chamadas seguras a partir da worker thread: só enfileiram -----------

    def _append_transcript(self, text):
        self._event_queue.put(('transcript', text))

    def _append_translation(self, text):
        self._event_queue.put(('translation', text))

    def _set_status(self, status):
        self._event_queue.put(('status', status))

    def _finish(self, final_state):
        self._event_queue.put(('finish', final_state))

    def _set_suggestion_status(self, status):
        self._event_queue.put(('suggestion_status', status))

    def _set_suggestion(self, text):
        self._event_queue.put(('suggestion', text))

    def _suggestion_done(self):
        self._event_queue.put(('suggestion_done', None))

    # -- processamento das filas, executado só na thread principal -----------

    def _drain_queue(self):
        while True:
            try:
                kind, payload = self._event_queue.get_nowait()
            except queue.Empty:
                break

            if kind == 'transcript':
                self._append_to(self.transcript_text, payload)
            elif kind == 'translation':
                self._append_to(self.translation_text, payload)
            elif kind == 'status':
                self.status_var.set(payload)
            elif kind == 'finish':
                self._state = payload
                self._sync_controls()
            elif kind == 'suggestion_status':
                self.suggest_status_var.set(payload)
            elif kind == 'suggestion':
                self._set_text_widget(self.suggest_text, payload)
            elif kind == 'suggestion_done':
                self._suggesting = False
                self.suggest_button.configure(state='normal')

        self.after(100, self._drain_queue)

    @staticmethod
    def _append_to(widget, text):
        if not text:
            return
        widget.configure(state='normal')
        widget.insert('end', text + '\n')
        widget.see('end')
        widget.configure(state='disabled')

    @staticmethod
    def _set_text_widget(widget, text):
        """Substitui todo o conteúdo em vez de acrescentar — usado pela
        sugestão de resposta, que nunca deve acumular texto de blocos
        antigos (ver docstring da classe)."""
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        if text:
            widget.insert('end', text)
        widget.configure(state='disabled')

    def _on_toggle(self):
        if self._state == 'idle':
            self._record_stop_event = threading.Event()
            self._state = 'recording'
            self._sync_controls()
            self._worker_thread = threading.Thread(target=self._run_cycle, daemon=True)
            self._worker_thread.start()
        elif self._state == 'recording':
            # Só sinaliza o fim da gravação. Transcrição, tradução e fala já
            # em andamento não são (nem precisam ser) interrompidas no meio.
            self._record_stop_event.set()
            self._state = 'processing'
            self._sync_controls()
        # em 'processing' o botão fica desabilitado; clique é ignorado.

    def _sync_controls(self):
        if self._state == 'idle':
            self.toggle_button.configure(text=LABEL_IDLE, state='normal')
            self.model_combo.configure(state='readonly')
            self.device_combo.configure(state='readonly')
            self.refresh_devices_button.configure(state='normal')
            self.target_lang_entry.configure(state='readonly')
            self.tts_engine_combo.configure(state='readonly')
        elif self._state == 'recording':
            self.toggle_button.configure(text=LABEL_RECORDING, state='normal')
            self.model_combo.configure(state='disabled')
            self.device_combo.configure(state='disabled')
            self.refresh_devices_button.configure(state='disabled')
            self.target_lang_entry.configure(state='disabled')
            self.tts_engine_combo.configure(state='disabled')
        else:  # processing
            self.toggle_button.configure(text=LABEL_PROCESSING, state='disabled')

    def shutdown(self):
        """Sinaliza para a worker thread encerrar; não bloqueia a saída do app."""
        self._record_stop_event.set()

    def _run_cycle(self):
        target_lang = self._selected_target_lang_code()
        model_size = self.model_var.get()
        device = self._selected_device_index()
        tts_engine = self._selected_tts_engine()

        try:
            if self.model is None or self._loaded_model_size != model_size:
                self._set_status('Carregando modelo...')
                self.model = create_model(model_size=model_size, device='auto')
                self._loaded_model_size = model_size

            self._set_status('Ouvindo...')
            audio_data = record_utterance(sample_rate=SAMPLE_RATE, device=device,
                                           stop_event=self._record_stop_event)
            if audio_data is None:
                self._append_transcript('[Nenhuma fala detectada.]')
                return

            self._set_status('Transcrevendo...')
            text, detected_lang, probability = transcribe(self.model, audio_data)
            if not text:
                self._append_transcript('[Transcrição vazia.]')
                return
            self._append_transcript(text)

            # Guarda a fala mais recente, no idioma original, para o botão
            # "Sugerir resposta" — sobrescreve a anterior, nunca acumula.
            self._last_block_text = text
            self._last_block_lang = detected_lang

            self._set_status('Traduzindo...')
            translated_text = translate(text, detected_lang, target_lang)
            self._append_translation(translated_text)

            self._set_status('Falando...')
            speak(translated_text, target_lang, engine=tts_engine)
        except Exception as exc:
            self._append_transcript(f'[Erro: {exc}]')
        finally:
            self._set_status('')
            self._finish('idle')

    # -- botão "Sugerir resposta" (API Gemini) --------------------------------

    def _on_suggest_click(self):
        if self._suggesting:
            return
        text = self._last_block_text
        if not text:
            self.suggest_status_var.set('Grave uma fala para sugerir uma resposta.')
            return

        lang_code = self._last_block_lang
        lang_label = next((label for code, label in LANGUAGES if code == lang_code), lang_code or '')

        self._suggesting = True
        self.suggest_button.configure(state='disabled')
        self.suggest_status_var.set('Gerando sugestão...')
        threading.Thread(target=self._suggest_worker, args=(text, lang_label), daemon=True).start()

    def _suggest_worker(self, text, lang_label):
        try:
            suggestion = suggest_reply(text, lang_label)
            self._set_suggestion(suggestion or '(sem sugestão)')
            self._set_suggestion_status('')
        except Exception as exc:
            self._set_suggestion_status(f'Erro: {exc}')
        finally:
            self._suggestion_done()


class App:
    def __init__(self, root):
        self.root = root
        self.root.title('SpeakTranslate')
        self.root.geometry('640x560')
        self.root.minsize(560, 420)

        notebook = ttk.Notebook(root)
        notebook.pack(fill='both', expand=True)

        self.initial_tab = InitialTranslationTab(notebook)
        notebook.add(self.initial_tab, text='Tradução Inicial')

        self.streaming_tab = StreamingTranslationTab(notebook)
        notebook.add(self.streaming_tab, text='Tradução por Streaming')

        self.virtual_mic_tab = VirtualMicTab(notebook)
        notebook.add(self.virtual_mic_tab, text='Microfone Virtual')

        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    def _on_close(self):
        self.initial_tab.shutdown()
        self.streaming_tab.shutdown()
        self.virtual_mic_tab.shutdown()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
