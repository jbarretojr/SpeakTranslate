import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

from app_constants import LANGUAGES, TTS_ENGINES, WHISPER_MODELS
from audio_capture import list_input_devices, record_utterance
from streaming_gui import StreamingTranslationTab
from transcription import create_model, transcribe
from translation import translate
from tts import speak

SAMPLE_RATE = 16000
DEFAULT_MODEL = 'base'
DEFAULT_TARGET_LANG = 'pt'

# Rótulos do botão de alternância, no mesmo espírito do atalho
# Ctrl+Shift+Space do VoiceNote: um clique inicia a gravação, o próximo
# apenas sinaliza "parar de gravar agora" — a partir daí transcrição,
# tradução e fala rodam até o fim sem chance de serem interrompidas no meio.
LABEL_IDLE = '🎙 Iniciar Gravação'
LABEL_RECORDING = '⏹ Parar Gravação'
LABEL_PROCESSING = 'Processando...'


class InitialTranslationTab(ttk.Frame):
    """
    Aba "Tradução Inicial": grava uma fala por vez (toggle iniciar/parar
    gravação), transcreve, traduz e fala o resultado. Comportamento
    inalterado em relação à versão original de tela única do app.
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

        self._build_widgets()
        self._refresh_devices()
        self.after(100, self._drain_queue)

    def _build_widgets(self):
        options_frame = ttk.Frame(self, padding=10)
        options_frame.pack(fill='x')

        ttk.Label(options_frame, text='Idioma de destino:').grid(row=0, column=0, sticky='w')
        default_label = next(
            (label for code, label in LANGUAGES if code == DEFAULT_TARGET_LANG), LANGUAGES[0][1])
        self.target_lang_var = tk.StringVar(value=default_label)
        self.target_lang_entry = ttk.Combobox(
            options_frame, textvariable=self.target_lang_var, width=12, state='readonly',
            values=[label for _, label in LANGUAGES])
        self.target_lang_entry.grid(row=0, column=1, sticky='w', padx=(4, 16))

        ttk.Label(options_frame, text='Modelo Whisper:').grid(row=0, column=2, sticky='w')
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.model_combo = ttk.Combobox(options_frame, textvariable=self.model_var, width=10,
                                         values=WHISPER_MODELS, state='readonly')
        self.model_combo.grid(row=0, column=3, sticky='w', padx=4)

        ttk.Label(options_frame, text='Entrada de áudio:').grid(row=1, column=0, sticky='w', pady=(8, 0))
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(options_frame, textvariable=self.device_var, width=38, state='readonly')
        self.device_combo.grid(row=1, column=1, columnspan=2, sticky='we', padx=4, pady=(8, 0))
        self.refresh_devices_button = ttk.Button(options_frame, text='Atualizar', command=self._refresh_devices)
        self.refresh_devices_button.grid(row=1, column=3, sticky='w', padx=4, pady=(8, 0))

        ttk.Label(options_frame, text='Motor de voz:').grid(row=2, column=0, sticky='w', pady=(8, 0))
        default_tts_label = TTS_ENGINES[0][1]
        self.tts_engine_var = tk.StringVar(value=default_tts_label)
        self.tts_engine_combo = ttk.Combobox(
            options_frame, textvariable=self.tts_engine_var, width=14, state='readonly',
            values=[label for _, label in TTS_ENGINES])
        self.tts_engine_combo.grid(row=2, column=1, sticky='w', padx=(4, 16), pady=(8, 0))

        self.status_var = tk.StringVar(value='Ocioso')
        ttk.Label(self, textvariable=self.status_var, font=('TkDefaultFont', 13, 'bold')).pack(pady=(8, 4))

        button_frame = ttk.Frame(self)
        button_frame.pack(pady=4)
        self.toggle_button = ttk.Button(button_frame, text=LABEL_IDLE, command=self._on_toggle)
        self.toggle_button.pack(side='left', padx=6)

        self.log_text = scrolledtext.ScrolledText(self, height=16, state='disabled', wrap='word')
        self.log_text.pack(fill='both', expand=True, padx=10, pady=10)

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

    def _log(self, message):
        self._event_queue.put(('log', message))

    def _set_status(self, status):
        self._event_queue.put(('status', status))

    def _finish(self, final_state):
        self._event_queue.put(('finish', final_state))

    # -- processamento das filas, executado só na thread principal -----------

    def _drain_queue(self):
        while True:
            try:
                kind, payload = self._event_queue.get_nowait()
            except queue.Empty:
                break

            if kind == 'log':
                self.log_text.configure(state='normal')
                self.log_text.insert('end', payload + '\n')
                self.log_text.see('end')
                self.log_text.configure(state='disabled')
            elif kind == 'status':
                self.status_var.set(payload)
            elif kind == 'finish':
                self._state = payload
                self._sync_controls()

        self.after(100, self._drain_queue)

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
                self._log(f'Carregando modelo Whisper "{model_size}"...')
                self.model = create_model(model_size=model_size, device='auto')
                self._loaded_model_size = model_size
                self._log('Modelo carregado.')

            self._set_status('Ouvindo...')
            audio_data = record_utterance(sample_rate=SAMPLE_RATE, device=device,
                                           stop_event=self._record_stop_event)
            if audio_data is None:
                self._log('Nenhuma fala detectada.')
                return

            self._set_status('Transcrevendo...')
            text, detected_lang, probability = transcribe(self.model, audio_data)
            if not text:
                self._log('Transcrição vazia.')
                return
            self._log(f'[{detected_lang} ({probability:.0%})] {text}')

            self._set_status('Traduzindo...')
            translated_text = translate(text, detected_lang, target_lang)
            self._log(f'[{target_lang}] {translated_text}')

            self._set_status('Falando...')
            speak(translated_text, target_lang, engine=tts_engine)
        except Exception as exc:
            self._log(f'Erro ao processar a frase: {exc}')
        finally:
            self._set_status('Ocioso')
            self._finish('idle')


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

        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    def _on_close(self):
        self.initial_tab.shutdown()
        self.streaming_tab.shutdown()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
