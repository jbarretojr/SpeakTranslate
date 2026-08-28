import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

from app_constants import LANGUAGES, WHISPER_MODELS
from audio_capture import ContinuousAudioCapture, list_input_devices
from stream_transcription import LocalAgreementTranscriber
from transcription import create_model
from translation import translate

SAMPLE_RATE = 16000
DEFAULT_MODEL = 'base'
DEFAULT_SOURCE_LANG = 'en'
DEFAULT_TARGET_LANG = 'pt'
PROCESS_INTERVAL_S = 1.0  # intervalo entre passagens de re-transcrição

AUTO_DETECT_LABEL = 'Detectar automaticamente'

LABEL_IDLE = '▶ Iniciar Transcrição'
LABEL_RUNNING = '⏹ Parar'


class StreamingTranslationTab(ttk.Frame):
    """
    Aba "Tradução por Streaming": pensada para reuniões (Meet/Zoom/Teams) —
    transcreve e traduz continuamente enquanto a pessoa fala, sem esperar uma
    pausa (veja stream_transcription.py para a técnica usada). Só "escuta";
    a função de "Resposta" (falar de volta na reunião em outro idioma) fica
    para uma próxima etapa.
    """

    def __init__(self, master):
        super().__init__(master, padding=0)

        self.model = None
        self._loaded_model_size = None
        self._event_queue = queue.Queue()

        self._running = False
        self._stop_event = threading.Event()
        self._worker_thread = None
        self._input_devices = []

        self._build_widgets()
        self._refresh_devices()
        self.after(100, self._drain_queue)

    def _build_widgets(self):
        options_frame = ttk.Frame(self, padding=10)
        options_frame.pack(fill='x')

        ttk.Label(options_frame, text='Idioma de origem:').grid(row=0, column=0, sticky='w')
        source_values = [AUTO_DETECT_LABEL] + [label for _, label in LANGUAGES]
        default_source_label = next(
            (label for code, label in LANGUAGES if code == DEFAULT_SOURCE_LANG), source_values[0])
        self.source_lang_var = tk.StringVar(value=default_source_label)
        self.source_lang_combo = ttk.Combobox(
            options_frame, textvariable=self.source_lang_var, width=18,
            state='readonly', values=source_values)
        self.source_lang_combo.grid(row=0, column=1, sticky='w', padx=(4, 16))

        ttk.Label(options_frame, text='Idioma de destino:').grid(row=0, column=2, sticky='w')
        default_target_label = next(
            (label for code, label in LANGUAGES if code == DEFAULT_TARGET_LANG), LANGUAGES[0][1])
        self.target_lang_var = tk.StringVar(value=default_target_label)
        self.target_lang_combo = ttk.Combobox(
            options_frame, textvariable=self.target_lang_var, width=12,
            state='readonly', values=[label for _, label in LANGUAGES])
        self.target_lang_combo.grid(row=0, column=3, sticky='w', padx=4)

        ttk.Label(options_frame, text='Modelo Whisper:').grid(row=1, column=0, sticky='w', pady=(8, 0))
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.model_combo = ttk.Combobox(options_frame, textvariable=self.model_var, width=10,
                                         state='readonly', values=WHISPER_MODELS)
        self.model_combo.grid(row=1, column=1, sticky='w', padx=(4, 16), pady=(8, 0))

        ttk.Label(options_frame, text='Entrada de áudio:').grid(row=2, column=0, sticky='w', pady=(8, 0))
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(options_frame, textvariable=self.device_var, width=38, state='readonly')
        self.device_combo.grid(row=2, column=1, columnspan=2, sticky='we', padx=4, pady=(8, 0))
        self.refresh_devices_button = ttk.Button(options_frame, text='Atualizar', command=self._refresh_devices)
        self.refresh_devices_button.grid(row=2, column=3, sticky='w', padx=4, pady=(8, 0))

        hint = ('Dica: para transcrever uma reunião (Meet/Zoom/Teams), selecione aqui o dispositivo de '
                'loopback de áudio (ex.: "BlackHole 2ch") em vez do microfone. Modelos menores (tiny/base) '
                'respondem mais rápido; recomendado para uso em tempo real.')
        ttk.Label(self, text=hint, wraplength=600, foreground='#666').pack(fill='x', padx=10, pady=(0, 4))

        self.status_var = tk.StringVar(value='Ocioso')
        ttk.Label(self, textvariable=self.status_var, font=('TkDefaultFont', 13, 'bold')).pack(pady=(4, 4))

        button_frame = ttk.Frame(self)
        button_frame.pack(pady=4)
        self.toggle_button = ttk.Button(button_frame, text=LABEL_IDLE, command=self._on_toggle)
        self.toggle_button.pack(side='left', padx=6)

        self.preview_var = tk.StringVar(value='')
        ttk.Label(self, textvariable=self.preview_var, foreground='#888',
                  font=('TkDefaultFont', 10, 'italic'), wraplength=600, justify='left').pack(fill='x', padx=10)

        panes = ttk.Panedwindow(self, orient='horizontal')
        panes.pack(fill='both', expand=True, padx=10, pady=10)

        transcript_frame = ttk.Frame(panes)
        ttk.Label(transcript_frame, text='Transcrição (original)').pack(anchor='w')
        self.transcript_text = scrolledtext.ScrolledText(transcript_frame, height=16, state='disabled', wrap='word')
        self.transcript_text.pack(fill='both', expand=True)
        panes.add(transcript_frame, weight=1)

        translation_frame = ttk.Frame(panes)
        ttk.Label(translation_frame, text='Tradução').pack(anchor='w')
        self.translation_text = scrolledtext.ScrolledText(translation_frame, height=16, state='disabled', wrap='word')
        self.translation_text.pack(fill='both', expand=True)
        panes.add(translation_frame, weight=1)

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

    # -- chamadas seguras a partir da worker thread: só enfileiram -----------

    def _append_transcript(self, text):
        self._event_queue.put(('transcript', text))

    def _append_translation(self, text):
        self._event_queue.put(('translation', text))

    def _set_status(self, status):
        self._event_queue.put(('status', status))

    def _set_preview(self, text):
        self._event_queue.put(('preview', text))

    def _finish(self):
        self._event_queue.put(('finish', None))

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
            elif kind == 'finish':
                self._running = False
                self._sync_controls()

        self.after(100, self._drain_queue)

    @staticmethod
    def _append_to(widget, text):
        if not text:
            return
        widget.configure(state='normal')
        widget.insert('end', text + ' ')
        widget.see('end')
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
            self.source_lang_combo.configure(state='readonly')
            self.target_lang_combo.configure(state='readonly')
            self.model_combo.configure(state='readonly')
            self.device_combo.configure(state='readonly')
            self.refresh_devices_button.configure(state='normal')
        else:
            self.toggle_button.configure(text=LABEL_RUNNING, state='normal')
            self.source_lang_combo.configure(state='disabled')
            self.target_lang_combo.configure(state='disabled')
            self.model_combo.configure(state='disabled')
            self.device_combo.configure(state='disabled')
            self.refresh_devices_button.configure(state='disabled')

    def shutdown(self):
        """Sinaliza para a worker thread encerrar; não bloqueia a saída do app."""
        self._stop_event.set()

    def _run_loop(self):
        source_lang = self._selected_source_lang_code()
        target_lang = self._selected_target_lang_code()
        model_size = self.model_var.get()
        device = self._selected_device_index()

        capture = None
        try:
            if self.model is None or self._loaded_model_size != model_size:
                self._set_status('Carregando modelo...')
                self.model = create_model(model_size=model_size, device='auto')
                self._loaded_model_size = model_size

            engine = LocalAgreementTranscriber(self.model, sample_rate=SAMPLE_RATE, language=source_lang)
            last_detected_lang = source_lang or 'en'

            self._set_status('Ouvindo...')
            capture = ContinuousAudioCapture(sample_rate=SAMPLE_RATE, device=device)
            capture.start()

            while not self._stop_event.is_set():
                self._stop_event.wait(PROCESS_INTERVAL_S)
                engine.feed(capture.read_available())
                detected = self._process_once(engine, target_lang)
                if detected:
                    last_detected_lang = detected

            # dreno final: processa o que restou no buffer e fecha a frase pendente
            engine.feed(capture.read_available())
            detected = self._process_once(engine, target_lang)
            last_detected_lang = detected or last_detected_lang
            final_sentence = engine.flush()
            if final_sentence:
                self._translate_and_show(final_sentence, last_detected_lang, target_lang)

            self._set_status('Ocioso')
        except Exception as exc:
            self._append_transcript(f'\n[Erro: {exc}]')
            self._set_status('Erro')
        finally:
            if capture is not None:
                capture.stop()
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
            self._translate_and_show(result['sentence'], result['language'], target_lang)
        return result['language']

    def _translate_and_show(self, sentence, source_lang, target_lang):
        sentence = sentence.strip()
        if not sentence:
            return
        try:
            translated = translate(sentence, source_lang, target_lang)
        except Exception as exc:
            translated = f'[erro na tradução: {exc}]'
        self._append_translation(translated)
