import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

from app_constants import LANGUAGES, TTS_ENGINES, WHISPER_MODELS
import sounddevice as sd

from audio_capture import AudioMonitor, ContinuousAudioCapture, list_input_devices
from llm_suggest import suggest_reply
from stream_transcription import LocalAgreementTranscriber
from transcription import create_model
from translation import translate
from tts import speak_to_device

SAMPLE_RATE = 16000
DEFAULT_MODEL = 'base'
DEFAULT_SOURCE_LANG = 'en'
DEFAULT_TARGET_LANG = 'pt'
PROCESS_INTERVAL_S = 0.5  # intervalo entre passagens de re-transcrição

AUTO_DETECT_LABEL = 'Detectar automaticamente'

LABEL_IDLE = '▶ Iniciar Transcrição'
LABEL_RUNNING = '⏹ Parar'

REPLY_LABEL_IDLE = '🎤 Iniciar Resposta'
REPLY_LABEL_RUNNING = '⏹ Parar Resposta'


class StreamingTranslationTab(ttk.Frame):
    """
    Aba "Tradução por Streaming": pensada para reuniões (Meet/Zoom/Teams).

    Dois blocos independentes, que podem rodar ao mesmo tempo:
    - Transcrição/tradução (bloco principal, no centro): escuta a reunião
      (normalmente via um dispositivo de loopback como o BlackHole) e mostra
      a transcrição e tradução continuamente, sem esperar pausas na fala.
    - "Resposta" (rodapé, secundário, com seus próprios seletores de idioma
      "Eu falo" / "Idioma de destino"): captura o SEU microfone, transcreve,
      traduz e fala o resultado num dispositivo de saída escolhido (por
      padrão um driver de loopback como o BlackHole, que a chamada enxerga
      como "microfone") — mesmo mecanismo da aba "Microfone Virtual", só que
      alimentado ao vivo pela sua fala em vez de texto digitado. É a via de
      volta da mesma conversa do bloco principal.

    Ambos usam a mesma técnica de re-transcrição incremental (veja
    stream_transcription.py).
    """

    def __init__(self, master):
        super().__init__(master, padding=0)

        self.model = None
        self._loaded_model_size = None
        self._model_lock = threading.Lock()
        self._event_queue = queue.Queue()

        self._running = False
        self._stop_event = threading.Event()
        self._worker_thread = None
        self._input_devices = []
        self._monitor_output_devices = []
        self._last_preview_text = ''

        # Último bloco (sentença) fechado no bloco principal — usado pelo
        # botão "Sugerir resposta"; nunca acumula, só o mais recente importa.
        self._last_block_text = ''
        self._last_block_lang = None
        self._suggesting = False

        self._reply_running = False
        self._reply_stop_event = threading.Event()
        self._reply_worker_thread = None
        self._reply_input_devices = []
        self._reply_output_devices = []
        self._reply_last_preview_text = ''

        self._build_widgets()
        self._refresh_devices()
        self._refresh_monitor_devices()
        self._refresh_reply_devices()
        self._refresh_reply_output_devices()
        self.after(100, self._drain_queue)

    def _build_widgets(self):
        self._build_options_bar()
        self._build_control_row()
        self._build_main_panes()
        self._build_suggest_block()
        ttk.Separator(self, orient='horizontal').pack(fill='x', padx=10, pady=(0, 4))
        self._build_reply_block()

    def _build_options_bar(self):
        """Barra compacta de configuração: idiomas, modelo e entrada de áudio
        lado a lado, com rótulos curtos, para deixar mais espaço para a
        transcrição/tradução abaixo."""
        frame = ttk.Frame(self, padding=(10, 8, 10, 4))
        frame.pack(fill='x')

        ttk.Label(frame, text='Origem:').grid(row=0, column=0, sticky='w')
        source_values = [AUTO_DETECT_LABEL] + [label for _, label in LANGUAGES]
        default_source_label = next(
            (label for code, label in LANGUAGES if code == DEFAULT_SOURCE_LANG), source_values[0])
        self.source_lang_var = tk.StringVar(value=default_source_label)
        self.source_lang_combo = ttk.Combobox(
            frame, textvariable=self.source_lang_var, width=16,
            state='readonly', values=source_values)
        self.source_lang_combo.grid(row=0, column=1, sticky='w', padx=(4, 14))

        ttk.Label(frame, text='Destino:').grid(row=0, column=2, sticky='w')
        default_target_label = next(
            (label for code, label in LANGUAGES if code == DEFAULT_TARGET_LANG), LANGUAGES[0][1])
        self.target_lang_var = tk.StringVar(value=default_target_label)
        self.target_lang_combo = ttk.Combobox(
            frame, textvariable=self.target_lang_var, width=11,
            state='readonly', values=[label for _, label in LANGUAGES])
        self.target_lang_combo.grid(row=0, column=3, sticky='w', padx=(4, 14))

        ttk.Label(frame, text='Modelo:').grid(row=0, column=4, sticky='w')
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.model_combo = ttk.Combobox(frame, textvariable=self.model_var, width=8,
                                         state='readonly', values=WHISPER_MODELS)
        self.model_combo.grid(row=0, column=5, sticky='w', padx=4)

        ttk.Label(frame, text='Entrada:').grid(row=1, column=0, sticky='w', pady=(6, 0))
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(frame, textvariable=self.device_var, width=32, state='readonly')
        self.device_combo.grid(row=1, column=1, columnspan=3, sticky='we', padx=(4, 4), pady=(6, 0))
        self.refresh_devices_button = ttk.Button(frame, text='⟳', width=3, command=self._refresh_devices)
        self.refresh_devices_button.grid(row=1, column=4, sticky='w', pady=(6, 0))

        self.monitor_var = tk.BooleanVar(value=False)
        self.monitor_check = ttk.Checkbutton(
            frame, text='Monitorar:', variable=self.monitor_var,
            command=self._sync_monitor_device_state)
        self.monitor_check.grid(row=2, column=0, sticky='w', pady=(6, 0))
        self.monitor_device_var = tk.StringVar()
        self.monitor_device_combo = ttk.Combobox(
            frame, textvariable=self.monitor_device_var, width=32, state='disabled')
        self.monitor_device_combo.grid(row=2, column=1, columnspan=3, sticky='we', padx=(4, 4), pady=(6, 0))
        self.monitor_refresh_button = ttk.Button(
            frame, text='⟳', width=3, command=self._refresh_monitor_devices, state='disabled')
        self.monitor_refresh_button.grid(row=2, column=4, sticky='w', pady=(6, 0))

        hint = ('Dica: para reuniões (Meet/Zoom/Teams), selecione um dispositivo de loopback '
                '(ex.: "BlackHole 2ch") em "Entrada". Modelos menores (tiny/base) respondem mais rápido.')
        ttk.Label(frame, text=hint, wraplength=640, foreground='#888',
                  font=('TkDefaultFont', 9)).grid(row=3, column=0, columnspan=6, sticky='w', pady=(6, 0))

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
        """Transcrição e tradução são o foco principal da aba: ocupam a maior
        parte do espaço vertical, com fonte maior para leitura durante a
        reunião."""
        panes = ttk.Panedwindow(self, orient='horizontal')
        panes.pack(fill='both', expand=True, padx=10, pady=(4, 8))

        preview_kwargs = dict(foreground='#888', font=('TkDefaultFont', 10, 'italic'),
                               wraplength=290, justify='left', anchor='w')

        transcript_frame = ttk.Frame(panes)
        ttk.Label(transcript_frame, text='Transcrição (original)',
                  font=('TkDefaultFont', 11, 'bold')).pack(anchor='w')
        self.preview_var = tk.StringVar(value='')
        ttk.Label(transcript_frame, textvariable=self.preview_var, **preview_kwargs).pack(fill='x', pady=(0, 4))
        self.transcript_text = scrolledtext.ScrolledText(
            transcript_frame, height=20, state='disabled', wrap='word', font=('TkDefaultFont', 12))
        self.transcript_text.pack(fill='both', expand=True)
        panes.add(transcript_frame, weight=1)

        translation_frame = ttk.Frame(panes)
        ttk.Label(translation_frame, text='Tradução', font=('TkDefaultFont', 11, 'bold')).pack(anchor='w')
        self.preview_translation_var = tk.StringVar(value='')
        ttk.Label(translation_frame, textvariable=self.preview_translation_var, **preview_kwargs).pack(
            fill='x', pady=(0, 4))
        self.translation_text = scrolledtext.ScrolledText(
            translation_frame, height=20, state='disabled', wrap='word', font=('TkDefaultFont', 12))
        self.translation_text.pack(fill='both', expand=True)
        panes.add(translation_frame, weight=1)

    def _build_suggest_block(self):
        """Botão "Sugerir resposta": chama a API Gemini (llm_suggest.py) com
        o último bloco (sentença) fechado na transcrição e mostra uma
        sugestão de resposta no idioma de quem está falando — pensado para
        quem tem domínio intermediário desse idioma e só precisa ler ou
        pronunciar a sugestão. Cada clique SUBSTITUI a sugestão anterior
        (nunca acumula texto antigo + novo)."""
        frame = ttk.Frame(self, padding=(10, 0, 10, 8))
        frame.pack(fill='x')

        self.suggest_button = ttk.Button(
            frame, text='💡 Sugerir resposta', command=self._on_suggest_click)
        self.suggest_button.pack(side='left')
        self.suggest_status_var = tk.StringVar(value='')
        ttk.Label(frame, textvariable=self.suggest_status_var, foreground='#888').pack(
            side='left', padx=(10, 0))

        self.suggest_text = tk.Text(self, height=3, state='disabled', wrap='word', padx=10, pady=6)
        self.suggest_text.pack(fill='x', padx=10, pady=(0, 8))

    def _build_reply_block(self):
        """Bloco "Resposta", compacto e no rodapé da aba — é um recurso
        secundário em relação à transcrição/tradução da reunião acima."""
        frame = ttk.Frame(self, padding=(10, 6, 10, 8))
        frame.pack(fill='x')

        ttk.Label(frame, text='Resposta (microfone → transcreve → traduz → fala)',
                  font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, columnspan=6, sticky='w')

        # Idiomas próprios deste bloco (não compartilhados com o bloco
        # principal) — evita a confusão de reaproveitar "Origem"/"Destino"
        # com papéis invertidos.
        ttk.Label(frame, text='Eu falo:').grid(row=1, column=0, sticky='w', pady=(4, 0))
        default_my_lang_label = next(
            (label for code, label in LANGUAGES if code == DEFAULT_TARGET_LANG), LANGUAGES[0][1])
        self.reply_my_lang_var = tk.StringVar(value=default_my_lang_label)
        self.reply_my_lang_combo = ttk.Combobox(
            frame, textvariable=self.reply_my_lang_var, width=16, state='readonly',
            values=[label for _, label in LANGUAGES])
        self.reply_my_lang_combo.grid(row=1, column=1, sticky='w', padx=4, pady=(4, 0))

        ttk.Label(frame, text='Idioma de destino:').grid(row=1, column=3, sticky='w', padx=(14, 0), pady=(4, 0))
        default_output_lang_label = next(
            (label for code, label in LANGUAGES if code == DEFAULT_SOURCE_LANG), LANGUAGES[0][1])
        self.reply_output_lang_var = tk.StringVar(value=default_output_lang_label)
        self.reply_output_lang_combo = ttk.Combobox(
            frame, textvariable=self.reply_output_lang_var, width=14, state='readonly',
            values=[label for _, label in LANGUAGES])
        self.reply_output_lang_combo.grid(row=1, column=4, sticky='w', padx=4, pady=(4, 0))

        ttk.Label(frame, text='Microfone:').grid(row=2, column=0, sticky='w', pady=(4, 0))
        self.reply_device_var = tk.StringVar()
        self.reply_device_combo = ttk.Combobox(frame, textvariable=self.reply_device_var, width=24, state='readonly')
        self.reply_device_combo.grid(row=2, column=1, sticky='we', padx=4, pady=(4, 0))
        self.reply_refresh_devices_button = ttk.Button(
            frame, text='⟳', width=3, command=self._refresh_reply_devices)
        self.reply_refresh_devices_button.grid(row=2, column=2, sticky='w', pady=(4, 0))

        ttk.Label(frame, text='Voz:').grid(row=2, column=3, sticky='w', padx=(14, 0), pady=(4, 0))
        default_tts_label = TTS_ENGINES[0][1]
        self.reply_tts_engine_var = tk.StringVar(value=default_tts_label)
        self.reply_tts_engine_combo = ttk.Combobox(
            frame, textvariable=self.reply_tts_engine_var, width=12, state='readonly',
            values=[label for _, label in TTS_ENGINES])
        self.reply_tts_engine_combo.grid(row=2, column=4, sticky='w', padx=4, pady=(4, 0))

        # Saída: por padrão um dispositivo de loopback (ex.: BlackHole), para
        # que a fala traduzida vá direto pro "microfone virtual" que a chamada
        # (Zoom/Meet/Teams) enxerga — em vez de tocar nos alto-falantes.
        ttk.Label(frame, text='Saída:').grid(row=3, column=0, sticky='w', pady=(4, 0))
        self.reply_output_device_var = tk.StringVar()
        self.reply_output_device_combo = ttk.Combobox(
            frame, textvariable=self.reply_output_device_var, width=24, state='readonly')
        self.reply_output_device_combo.grid(row=3, column=1, sticky='we', padx=4, pady=(4, 0))
        self.reply_refresh_output_devices_button = ttk.Button(
            frame, text='⟳', width=3, command=self._refresh_reply_output_devices)
        self.reply_refresh_output_devices_button.grid(row=3, column=2, sticky='w', pady=(4, 0))

        self.reply_toggle_button = ttk.Button(frame, text=REPLY_LABEL_IDLE, command=self._on_reply_toggle)
        self.reply_toggle_button.grid(row=3, column=4, columnspan=2, sticky='e', padx=(14, 0), pady=(4, 0))

        self.reply_status_var = tk.StringVar(value='')
        ttk.Label(frame, textvariable=self.reply_status_var).grid(
            row=4, column=0, columnspan=6, sticky='w', pady=(4, 0))

        preview_kwargs = dict(foreground='#888', font=('TkDefaultFont', 9, 'italic'), anchor='w')
        self.reply_preview_var = tk.StringVar(value='')
        ttk.Label(frame, textvariable=self.reply_preview_var, wraplength=280, justify='left',
                  **preview_kwargs).grid(row=5, column=0, columnspan=3, sticky='we', pady=(2, 0))
        self.reply_preview_translation_var = tk.StringVar(value='')
        ttk.Label(frame, textvariable=self.reply_preview_translation_var, wraplength=280, justify='left',
                  **preview_kwargs).grid(row=5, column=3, columnspan=3, sticky='we', pady=(2, 0))

        self.reply_log_text = scrolledtext.ScrolledText(frame, height=3, state='disabled', wrap='word')
        self.reply_log_text.grid(row=6, column=0, columnspan=6, sticky='we', pady=(4, 0))

        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(4, weight=1)

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

    def _refresh_monitor_devices(self):
        previous = self.monitor_device_var.get()
        devices = sd.query_devices()
        self._monitor_output_devices = [
            (i, d['name']) for i, d in enumerate(devices) if d.get('max_output_channels', 0) > 0
        ]
        labels = [f'{i}: {name}' for i, name in self._monitor_output_devices]
        self.monitor_device_combo.configure(values=labels)
        if previous in labels:
            self.monitor_device_var.set(previous)
        else:
            # Padrão: um dispositivo de saída de verdade (não outro driver de
            # loopback), já que o objetivo aqui é ouvir com os próprios ouvidos.
            real_output = next((label for label in labels if 'blackhole' not in label.lower()), None)
            self.monitor_device_var.set(real_output or (labels[0] if labels else ''))

    def _selected_monitor_device_index(self):
        label = self.monitor_device_var.get()
        if not label:
            return None
        return int(label.split(':', 1)[0])

    def _sync_monitor_device_state(self):
        state = 'readonly' if self.monitor_var.get() and not self._running else 'disabled'
        self.monitor_device_combo.configure(state=state)
        self.monitor_refresh_button.configure(
            state='normal' if self.monitor_var.get() and not self._running else 'disabled')

    def _refresh_reply_devices(self):
        previous = self.reply_device_var.get()
        devices = list_input_devices()
        self._reply_input_devices = [
            (i, d['name']) for i, d in enumerate(devices) if d.get('max_input_channels', 0) > 0
        ]
        labels = [f'{i}: {name}' for i, name in self._reply_input_devices]
        self.reply_device_combo.configure(values=labels)
        if previous in labels:
            self.reply_device_var.set(previous)
        else:
            # Padrão: microfone interno do MacBook Air, já que o bloco
            # "Resposta" é pensado para uso com fone de ouvido no mic interno.
            internal = next((label for label in labels if 'macbook air' in label.lower()), None)
            self.reply_device_var.set(internal or (labels[0] if labels else ''))

    def _selected_reply_device_index(self):
        label = self.reply_device_var.get()
        if not label:
            return None
        return int(label.split(':', 1)[0])

    def _refresh_reply_output_devices(self):
        previous = self.reply_output_device_var.get()
        devices = sd.query_devices()
        self._reply_output_devices = [
            (i, d['name']) for i, d in enumerate(devices) if d.get('max_output_channels', 0) > 0
        ]
        labels = [f'{i}: {name}' for i, name in self._reply_output_devices]
        self.reply_output_device_combo.configure(values=labels)
        if previous in labels:
            self.reply_output_device_var.set(previous)
        else:
            # Padrão: um driver de loopback (ex.: BlackHole), já que o
            # objetivo deste bloco é alimentar o "microfone virtual" que a
            # chamada enxerga, não os alto-falantes de verdade.
            loopback = next((label for label in labels if 'blackhole' in label.lower()), None)
            self.reply_output_device_var.set(loopback or (labels[0] if labels else ''))

    def _selected_reply_output_device_index(self):
        label = self.reply_output_device_var.get()
        if not label:
            return None
        return int(label.split(':', 1)[0])

    def _selected_source_lang_code(self):
        label = self.source_lang_var.get()
        if label == AUTO_DETECT_LABEL:
            return None
        for code, lang_label in LANGUAGES:
            if lang_label == label:
                return code
        return None

    def _selected_target_lang_code(self):
        label = self.target_lang_var.get()
        for code, lang_label in LANGUAGES:
            if lang_label == label:
                return code
        return DEFAULT_TARGET_LANG

    def _selected_reply_my_lang_code(self):
        label = self.reply_my_lang_var.get()
        for code, lang_label in LANGUAGES:
            if lang_label == label:
                return code
        return DEFAULT_TARGET_LANG

    def _selected_reply_output_lang_code(self):
        label = self.reply_output_lang_var.get()
        for code, lang_label in LANGUAGES:
            if lang_label == label:
                return code
        return DEFAULT_SOURCE_LANG

    def _selected_reply_tts_engine(self):
        label = self.reply_tts_engine_var.get()
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

    def _set_preview(self, text):
        self._event_queue.put(('preview', text))

    def _set_preview_translation(self, text):
        self._event_queue.put(('preview_translation', text))

    def _finish(self):
        self._event_queue.put(('finish', None))

    def _set_suggestion_status(self, status):
        self._event_queue.put(('suggestion_status', status))

    def _set_suggestion(self, text):
        self._event_queue.put(('suggestion', text))

    def _suggestion_done(self):
        self._event_queue.put(('suggestion_done', None))

    def _reply_log(self, text):
        self._event_queue.put(('reply_log', text))

    def _set_reply_status(self, status):
        self._event_queue.put(('reply_status', status))

    def _set_reply_preview(self, text):
        self._event_queue.put(('reply_preview', text))

    def _set_reply_preview_translation(self, text):
        self._event_queue.put(('reply_preview_translation', text))

    def _reply_finish(self):
        self._event_queue.put(('reply_finish', None))

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
            elif kind == 'preview':
                self.preview_var.set(payload)
            elif kind == 'preview_translation':
                self.preview_translation_var.set(payload)
            elif kind == 'finish':
                self._running = False
                self._sync_controls()
            elif kind == 'suggestion_status':
                self.suggest_status_var.set(payload)
            elif kind == 'suggestion':
                self._set_text_widget(self.suggest_text, payload)
            elif kind == 'suggestion_done':
                self._suggesting = False
                self.suggest_button.configure(state='normal')
            elif kind == 'reply_log':
                self._append_to(self.reply_log_text, payload)
            elif kind == 'reply_status':
                self.reply_status_var.set(payload)
            elif kind == 'reply_preview':
                self.reply_preview_var.set(payload)
            elif kind == 'reply_preview_translation':
                self.reply_preview_translation_var.set(payload)
            elif kind == 'reply_finish':
                self._reply_running = False
                self._sync_reply_controls()

        self.after(100, self._drain_queue)

    @staticmethod
    def _append_to(widget, text):
        if not text:
            return
        widget.configure(state='normal')
        widget.insert('end', text + ' ')
        widget.see('end')
        widget.configure(state='disabled')

    @staticmethod
    def _set_text_widget(widget, text):
        """Como _append_to, mas SUBSTITUI todo o conteúdo em vez de
        acrescentar — usado pela sugestão de resposta, que nunca deve
        acumular texto de blocos antigos."""
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        if text:
            widget.insert('end', text)
        widget.configure(state='disabled')

    def _on_toggle(self):
        if not self._running:
            self._stop_event = threading.Event()
            self._running = True
            self._sync_controls()
            self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._worker_thread.start()
        else:
            # Sinaliza o encerramento; a worker thread termina o processamento
            # em andamento (bem mais curto que uma passagem inteira de
            # transcrição) e avisa via fila quando puder reativar os controles.
            self._stop_event.set()
            self.toggle_button.configure(state='disabled')

    def _sync_controls(self):
        if not self._running:
            self.toggle_button.configure(text=LABEL_IDLE, state='normal')
            self.device_combo.configure(state='readonly')
            self.refresh_devices_button.configure(state='normal')
            self.monitor_check.configure(state='normal')
        else:
            self.toggle_button.configure(text=LABEL_RUNNING, state='normal')
            self.device_combo.configure(state='disabled')
            self.refresh_devices_button.configure(state='disabled')
            self.monitor_check.configure(state='disabled')
        self._sync_monitor_device_state()
        self._sync_shared_controls()

    def _on_reply_toggle(self):
        if not self._reply_running:
            if self._selected_reply_output_device_index() is None:
                self._reply_log('[Nenhum dispositivo de saída disponível para "Saída".]')
                return
            self._reply_stop_event = threading.Event()
            self._reply_running = True
            self._sync_reply_controls()
            self._reply_worker_thread = threading.Thread(target=self._reply_run_loop, daemon=True)
            self._reply_worker_thread.start()
        else:
            self._reply_stop_event.set()
            self.reply_toggle_button.configure(state='disabled')

    def _sync_reply_controls(self):
        if not self._reply_running:
            self.reply_toggle_button.configure(text=REPLY_LABEL_IDLE, state='normal')
            self.reply_my_lang_combo.configure(state='readonly')
            self.reply_output_lang_combo.configure(state='readonly')
            self.reply_device_combo.configure(state='readonly')
            self.reply_refresh_devices_button.configure(state='normal')
            self.reply_output_device_combo.configure(state='readonly')
            self.reply_refresh_output_devices_button.configure(state='normal')
            self.reply_tts_engine_combo.configure(state='readonly')
        else:
            self.reply_toggle_button.configure(text=REPLY_LABEL_RUNNING, state='normal')
            self.reply_my_lang_combo.configure(state='disabled')
            self.reply_output_lang_combo.configure(state='disabled')
            self.reply_device_combo.configure(state='disabled')
            self.reply_refresh_devices_button.configure(state='disabled')
            self.reply_output_device_combo.configure(state='disabled')
            self.reply_refresh_output_devices_button.configure(state='disabled')
            self.reply_tts_engine_combo.configure(state='disabled')
        self._sync_shared_controls()

    def _sync_shared_controls(self):
        # O modelo Whisper é compartilhado pelos dois blocos; os idiomas já
        # não são mais (cada bloco tem seus próprios seletores).
        self.source_lang_combo.configure(state='readonly' if not self._running else 'disabled')
        self.target_lang_combo.configure(state='readonly' if not self._running else 'disabled')
        self.model_combo.configure(state='readonly' if not (self._running or self._reply_running) else 'disabled')

    def shutdown(self):
        """Sinaliza para as worker threads encerrarem; não bloqueia a saída do app."""
        self._stop_event.set()
        self._reply_stop_event.set()

    def _get_model(self, model_size, on_status=None):
        """Carrega (ou reaproveita) o modelo Whisper. Compartilhado entre os
        dois blocos (Resposta e Transcrição), protegido por lock já que
        ambos podem tentar carregar ao mesmo tempo se iniciados juntos."""
        with self._model_lock:
            if self.model is None or self._loaded_model_size != model_size:
                if on_status:
                    on_status('Carregando modelo...')
                self.model = create_model(model_size=model_size, device='auto')
                self._loaded_model_size = model_size
            return self.model

    def _run_loop(self):
        source_lang = self._selected_source_lang_code()
        target_lang = self._selected_target_lang_code()
        model_size = self.model_var.get()
        device = self._selected_device_index()
        monitor_enabled = self.monitor_var.get()
        monitor_device = self._selected_monitor_device_index()

        capture = None
        monitor = None
        try:
            self.model = self._get_model(model_size, on_status=self._set_status)

            engine = LocalAgreementTranscriber(self.model, sample_rate=SAMPLE_RATE, language=source_lang)
            last_detected_lang = source_lang or 'en'
            self._last_preview_text = ''

            self._set_status('Ouvindo...')
            capture = ContinuousAudioCapture(sample_rate=SAMPLE_RATE, device=device)
            capture.start()

            if monitor_enabled and monitor_device is not None:
                monitor = AudioMonitor(output_device=monitor_device, sample_rate=SAMPLE_RATE)
                monitor.start()

            while not self._stop_event.is_set():
                self._stop_event.wait(PROCESS_INTERVAL_S)
                audio_chunk = capture.read_available()
                engine.feed(audio_chunk)
                if monitor is not None:
                    monitor.feed(audio_chunk)
                detected = self._process_once(engine, target_lang)
                if detected:
                    last_detected_lang = detected

            # dreno final: processa o que restou no buffer e fecha a frase pendente
            audio_chunk = capture.read_available()
            engine.feed(audio_chunk)
            if monitor is not None:
                monitor.feed(audio_chunk)
            detected = self._process_once(engine, target_lang)
            last_detected_lang = detected or last_detected_lang
            final_sentence = engine.flush()
            if final_sentence:
                self._translate_and_show(final_sentence, last_detected_lang, target_lang)

            self._set_preview('')
            self._set_preview_translation('')
            self._set_status('')
        except Exception as exc:
            self._append_transcript(f'\n[Erro: {exc}]')
            self._set_status('Erro')
        finally:
            if capture is not None:
                capture.stop()
            if monitor is not None:
                monitor.stop()
            self._finish()

    def _process_once(self, engine, target_lang):
        """Roda uma passagem de re-transcrição. Retorna o idioma detectado, se houve passagem."""
        if not engine.has_pending_audio():
            return None
        result = engine.process()
        if result['committed']:
            self._append_transcript(result['committed'])
        self._set_preview(result['preview'])

        if result['sentence']:
            # Frase fechada: sai da prévia e vira texto definitivo no bloco.
            self._set_preview_translation('')
            self._translate_and_show(result['sentence'], result['language'], target_lang)
        else:
            # Traduz só o trechinho tentativo mais recente (o mesmo texto
            # mostrado na prévia da transcrição) — nunca acumula, é sempre
            # substituído a cada passagem, e por ser curto (poucas palavras)
            # a tradução sai quase imediata.
            self._update_preview_translation(result['preview'], result['language'], target_lang)

        return result['language']

    def _update_preview_translation(self, preview_text, source_lang, target_lang):
        preview_text = preview_text.strip()
        if preview_text == self._last_preview_text:
            return
        self._last_preview_text = preview_text
        if not preview_text:
            self._set_preview_translation('')
            return
        try:
            translated = translate(preview_text, source_lang, target_lang)
        except Exception:
            return  # falha na tradução provisória não é grave; a próxima passagem tenta de novo
        self._set_preview_translation(translated)

    def _translate_and_show(self, sentence, source_lang, target_lang):
        sentence = sentence.strip()
        if not sentence:
            return
        # Guarda o bloco (sentença fechada) mais recente, no idioma original,
        # para o botão "Sugerir resposta" — sobrescreve o anterior, nunca
        # acumula entre blocos.
        self._last_block_text = sentence
        self._last_block_lang = source_lang
        try:
            translated = translate(sentence, source_lang, target_lang)
        except Exception as exc:
            translated = f'[erro na tradução: {exc}]'
        self._append_translation(translated)

    # -- botão "Sugerir resposta" (API Gemini) --------------------------------

    def _on_suggest_click(self):
        if self._suggesting:
            return
        text = self._last_block_text
        if not text:
            self.suggest_status_var.set('Aguarde a transcrição de um trecho para sugerir uma resposta.')
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

    # -- bloco "Resposta": microfone -> transcrição -> tradução -> fala ------

    def _reply_run_loop(self):
        my_lang = self._selected_reply_my_lang_code()  # idioma que EU falo
        output_lang = self._selected_reply_output_lang_code()  # idioma em que a fala sai
        model_size = self.model_var.get()
        device = self._selected_reply_device_index()
        output_device = self._selected_reply_output_device_index()
        tts_engine = self._selected_reply_tts_engine()

        capture = None
        tts_queue = queue.Queue()
        tts_thread = threading.Thread(
            target=self._reply_tts_worker, args=(tts_queue, output_device), daemon=True)
        tts_thread.start()
        try:
            self.model = self._get_model(model_size, on_status=self._set_reply_status)

            # Fecha o trecho pendente a cada ~6 palavras (em vez de esperar a
            # frase inteira) para alimentar a fila de fala em pedaços
            # pequenos e frequentes — o cenário é sempre uso com fone de
            # ouvido, então não há risco de a fala sintetizada realimentar o
            # microfone enquanto a captura continua em paralelo.
            engine = LocalAgreementTranscriber(self.model, sample_rate=SAMPLE_RATE, language=my_lang,
                                                max_unpunctuated_words=6)
            self._reply_last_preview_text = ''

            self._set_reply_status('Ouvindo...')
            capture = ContinuousAudioCapture(sample_rate=SAMPLE_RATE, device=device)
            capture.start()

            while not self._reply_stop_event.is_set():
                self._reply_stop_event.wait(PROCESS_INTERVAL_S)
                engine.feed(capture.read_available())
                self._reply_process_once(engine, my_lang, output_lang, tts_engine, tts_queue)

            # dreno final: processa o que restou no buffer e enfileira a frase pendente
            engine.feed(capture.read_available())
            self._reply_process_once(engine, my_lang, output_lang, tts_engine, tts_queue)
            final_sentence = engine.flush()
            if final_sentence:
                self._reply_translate_and_enqueue(final_sentence, my_lang, output_lang, tts_engine, tts_queue)

            self._set_reply_preview('')
            self._set_reply_preview_translation('')

            # Deixa a fila de fala terminar o que já foi enfileirado antes de
            # marcar como ocioso, em vez de cortar a fala no meio.
            if not tts_queue.empty():
                self._set_reply_status('Finalizando fala...')
            tts_queue.put(None)
            tts_thread.join(timeout=30)

            self._set_reply_status('')
        except Exception as exc:
            self._reply_log(f'[Erro: {exc}]')
            self._set_reply_status('Erro')
        finally:
            if capture is not None:
                capture.stop()
            self._reply_finish()

    def _reply_tts_worker(self, tts_queue, output_device):
        """
        Consome a fila de fala numa thread separada, para que a captura e a
        transcrição do microfone nunca fiquem bloqueadas esperando o áudio
        anterior terminar de tocar — a pessoa pode continuar falando (e o
        app continua transcrevendo/traduzindo/enfileirando) enquanto uma
        fala anterior ainda está sendo reproduzida.

        A fala é sempre tocada no dispositivo de saída escolhido (por padrão
        um driver de loopback como o BlackHole), não no dispositivo padrão do
        sistema — é o mesmo mecanismo da aba "Microfone Virtual", só que
        alimentado pela transcrição/tradução ao vivo em vez de texto digitado.
        """
        while True:
            item = tts_queue.get()
            if item is None:
                return
            text, lang, tts_engine = item
            try:
                speak_to_device(text, lang, device=output_device, engine=tts_engine)
            except Exception as exc:
                self._reply_log(f'[erro ao falar: {exc}]')

    def _reply_process_once(self, engine, my_lang, output_lang, tts_engine, tts_queue):
        if not engine.has_pending_audio():
            return
        result = engine.process()
        self._set_reply_preview(result['preview'])

        if result['sentence']:
            # Trecho fechado (por pontuação, pausa, ou ~6 palavras sem
            # nenhuma das duas): vai pra fila de fala e some da prévia.
            self._set_reply_preview_translation('')
            self._reply_translate_and_enqueue(result['sentence'], my_lang, output_lang, tts_engine, tts_queue)
        else:
            # Mesma lógica do bloco de baixo: traduz só o trechinho curto e
            # tentativo mais recente, nunca acumula, é sempre substituído.
            self._reply_update_preview_translation(result['preview'], my_lang, output_lang)

    def _reply_update_preview_translation(self, preview_text, my_lang, output_lang):
        preview_text = preview_text.strip()
        if preview_text == self._reply_last_preview_text:
            return
        self._reply_last_preview_text = preview_text
        if not preview_text:
            self._set_reply_preview_translation('')
            return
        try:
            translated = translate(preview_text, my_lang, output_lang)
        except Exception:
            return  # falha na tradução provisória não é grave; a próxima passagem tenta de novo
        self._set_reply_preview_translation(translated)

    def _reply_translate_and_enqueue(self, sentence, my_lang, output_lang, tts_engine, tts_queue):
        sentence = sentence.strip()
        if not sentence:
            return
        try:
            translated = translate(sentence, my_lang, output_lang)
        except Exception as exc:
            self._reply_log(f'[erro na tradução: {exc}]')
            return
        self._reply_log(f'{sentence} -> {translated}')
        # Só enfileira — quem fala de fato é a _reply_tts_worker, numa
        # thread separada, para não bloquear a captura/transcrição enquanto
        # os trechos anteriores ainda estão sendo reproduzidos.
        tts_queue.put((translated, output_lang, tts_engine))
