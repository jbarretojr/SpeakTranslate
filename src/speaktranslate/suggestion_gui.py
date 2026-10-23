import queue
import threading
import tkinter as tk
from tkinter import ttk

from app_constants import LANGUAGES, WHISPER_MODELS
from audio_capture import ContinuousAudioCapture, list_input_devices
from stream_transcription import LocalAgreementTranscriber
from suggest_panel import SuggestReplyPanel
from transcription import create_model

SAMPLE_RATE = 16000
DEFAULT_MODEL = 'base'
PROCESS_INTERVAL_S = 0.5  # intervalo entre passagens de re-transcrição

AUTO_DETECT_LABEL = 'Detectar automaticamente'

LABEL_IDLE = '▶ Iniciar Transcrição'
LABEL_RUNNING = '⏹ Parar'
LABEL_STOPPING = 'Finalizando...'


class SuggestionTab(ttk.Frame):
    """
    Aba "Sugestão": só transcrição + sugestão de resposta, com o espaço da
    tela dedicado à resposta da IA.

    Captura contínua (mesma re-transcrição incremental das abas de tradução,
    ver stream_transcription.py), sem tradução nem voz. Cada frase fechada
    entra no campo "Conversa" do painel de sugestão (suggest_panel.py, layout
    'focus'), que ocupa todo o resto da aba — a sugestão fica num bloco
    grande que cresce com a janela, com rolagem para respostas longas.
    """

    def __init__(self, master):
        super().__init__(master, padding=0)

        self.model = None
        self._loaded_model_size = None

        # Toda comunicação da worker thread com a UI passa por esta fila,
        # drenada na thread principal (Tkinter não é thread-safe).
        self._event_queue = queue.Queue()

        # 'idle' | 'running' | 'stopping'
        self._state = 'idle'
        self._stop_event = threading.Event()
        self._worker_thread = None
        self._input_devices = []

        self._build_widgets()
        self._refresh_devices()
        self.after(100, self._drain_queue)

    def _build_widgets(self):
        frame = ttk.Frame(self, padding=(10, 8, 10, 4))
        frame.pack(fill='x')

        ttk.Label(frame, text='Origem:').grid(row=0, column=0, sticky='w')
        self.source_lang_var = tk.StringVar(value=AUTO_DETECT_LABEL)
        self.source_lang_combo = ttk.Combobox(
            frame, textvariable=self.source_lang_var, width=16, state='readonly',
            values=[AUTO_DETECT_LABEL] + [label for _, label in LANGUAGES])
        self.source_lang_combo.grid(row=0, column=1, sticky='w', padx=(4, 12))

        ttk.Label(frame, text='Modelo:').grid(row=0, column=2, sticky='w')
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.model_combo = ttk.Combobox(frame, textvariable=self.model_var, width=8,
                                         values=WHISPER_MODELS, state='readonly')
        self.model_combo.grid(row=0, column=3, sticky='w', padx=(4, 12))

        ttk.Label(frame, text='Entrada:').grid(row=0, column=4, sticky='w')
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(frame, textvariable=self.device_var, width=20, state='readonly')
        self.device_combo.grid(row=0, column=5, sticky='we', padx=(4, 4))
        self.refresh_devices_button = ttk.Button(frame, text='⟳', width=3, command=self._refresh_devices)
        self.refresh_devices_button.grid(row=0, column=6, sticky='w')
        frame.columnconfigure(5, weight=1)

        control = ttk.Frame(self, padding=(10, 2, 10, 4))
        control.pack(fill='x')
        self.toggle_button = ttk.Button(control, text=LABEL_IDLE, command=self._on_toggle)
        self.toggle_button.pack(side='left')
        self.status_var = tk.StringVar(value='')
        ttk.Label(control, textvariable=self.status_var, font=('TkDefaultFont', 11, 'bold')).pack(
            side='left', padx=(10, 0))
        # Hipótese provisória mais recente — só um sinal de que o áudio está
        # chegando; o texto confirmado vai para o campo "Conversa" abaixo.
        self.preview_var = tk.StringVar(value='')
        ttk.Label(control, textvariable=self.preview_var, foreground='#888',
                  font=('TkDefaultFont', 10, 'italic')).pack(side='left', padx=(10, 0), fill='x', expand=True)

        self.suggest_panel = SuggestReplyPanel(self, layout='focus')
        self.suggest_panel.pack(fill='both', expand=True, padx=10, pady=(0, 10))

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

    def _selected_source_lang_code(self):
        label = self.source_lang_var.get()
        for code, lang_label in LANGUAGES:
            if lang_label == label:
                return code
        return None  # detectar automaticamente

    # -- processamento da fila, executado só na thread principal -------------

    def _drain_queue(self):
        while True:
            try:
                kind, payload = self._event_queue.get_nowait()
            except queue.Empty:
                break

            if kind == 'status':
                self.status_var.set(payload)
            elif kind == 'preview':
                self.preview_var.set(payload)
            elif kind == 'sentence':
                self.suggest_panel.add_block(*payload)
            elif kind == 'finish':
                self._state = 'idle'
                self._sync_controls()

        self.after(100, self._drain_queue)

    def _on_toggle(self):
        if self._state == 'idle':
            self._stop_event = threading.Event()
            self._state = 'running'
            self._sync_controls()
            self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._worker_thread.start()
        elif self._state == 'running':
            self._stop_event.set()
            self._state = 'stopping'
            self._sync_controls()

    def _sync_controls(self):
        idle = self._state == 'idle'
        combo_state = 'readonly' if idle else 'disabled'
        self.source_lang_combo.configure(state=combo_state)
        self.model_combo.configure(state=combo_state)
        self.device_combo.configure(state=combo_state)
        self.refresh_devices_button.configure(state='normal' if idle else 'disabled')
        if self._state == 'idle':
            self.toggle_button.configure(text=LABEL_IDLE, state='normal')
        elif self._state == 'running':
            self.toggle_button.configure(text=LABEL_RUNNING, state='normal')
        else:  # stopping
            self.toggle_button.configure(text=LABEL_STOPPING, state='disabled')

    def shutdown(self):
        """Sinaliza para a worker thread encerrar; não bloqueia a saída do app."""
        self._stop_event.set()

    def _run_loop(self):
        source_lang = self._selected_source_lang_code()
        model_size = self.model_var.get()
        device = self._selected_device_index()

        capture = None
        try:
            if self.model is None or self._loaded_model_size != model_size:
                self._event_queue.put(('status', 'Carregando modelo...'))
                self.model = create_model(model_size=model_size, device='auto')
                self._loaded_model_size = model_size

            engine = LocalAgreementTranscriber(self.model, sample_rate=SAMPLE_RATE, language=source_lang)
            last_lang = source_lang

            self._event_queue.put(('status', 'Ouvindo...'))
            capture = ContinuousAudioCapture(sample_rate=SAMPLE_RATE, device=device)
            capture.start()

            while not self._stop_event.is_set():
                self._stop_event.wait(PROCESS_INTERVAL_S)
                engine.feed(capture.read_available())
                last_lang = self._process_once(engine) or last_lang

            # dreno final: processa o que restou no buffer e fecha a frase pendente
            engine.feed(capture.read_available())
            last_lang = self._process_once(engine) or last_lang
            final_sentence = engine.flush()
            if final_sentence:
                self._event_queue.put(('sentence', (final_sentence, last_lang)))
        except Exception as exc:
            self._event_queue.put(('status', f'Erro: {exc}'))
        else:
            self._event_queue.put(('status', ''))
        finally:
            if capture is not None:
                capture.stop()
            self._event_queue.put(('preview', ''))
            self._event_queue.put(('finish', None))

    def _process_once(self, engine):
        """Roda uma passagem de re-transcrição. Retorna o idioma detectado, se houve passagem."""
        if not engine.has_pending_audio():
            return None
        result = engine.process()
        self._event_queue.put(('preview', (result['pending'] + ' ' + result['preview']).strip()))
        if result['sentence']:
            self._event_queue.put(('sentence', (result['sentence'], result['language'])))
        return result['language']
