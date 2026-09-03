import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

import sounddevice as sd

from app_constants import LANGUAGES, TTS_ENGINES
from tts import speak_to_device

DEFAULT_TARGET_LANG = 'en'

LABEL_IDLE = '🔊 Falar no microfone virtual'
LABEL_SPEAKING = 'Falando...'


class VirtualMicTab(ttk.Frame):
    """
    Aba "Microfone Virtual": digite um texto, escolha o idioma de saída e
    toque a fala sintetizada num dispositivo de áudio virtual (ex.: BlackHole)
    em vez do dispositivo de saída padrão — quem está numa chamada com esse
    dispositivo configurado como microfone escuta; você não.

    Simples teste manual do mecanismo usado pelo bloco "Resposta" da aba de
    streaming, sem precisar falar no microfone nem esperar transcrição.
    """

    def __init__(self, master):
        super().__init__(master, padding=0)

        self._event_queue = queue.Queue()
        self._speaking = False
        self._output_devices = []

        self._build_widgets()
        self._refresh_devices()
        self.after(100, self._drain_queue)

    def _build_widgets(self):
        options_frame = ttk.Frame(self, padding=10)
        options_frame.pack(fill='x')

        ttk.Label(options_frame, text='Dispositivo de saída (microfone virtual):').grid(
            row=0, column=0, sticky='w', columnspan=2)
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(options_frame, textvariable=self.device_var, width=38, state='readonly')
        self.device_combo.grid(row=1, column=0, columnspan=2, sticky='we', padx=(0, 4), pady=(2, 0))
        self.refresh_devices_button = ttk.Button(options_frame, text='Atualizar', command=self._refresh_devices)
        self.refresh_devices_button.grid(row=1, column=2, sticky='w', pady=(2, 0))

        ttk.Label(options_frame, text='Idioma de saída:').grid(row=2, column=0, sticky='w', pady=(10, 0))
        default_lang_label = next(
            (label for code, label in LANGUAGES if code == DEFAULT_TARGET_LANG), LANGUAGES[0][1])
        self.lang_var = tk.StringVar(value=default_lang_label)
        self.lang_combo = ttk.Combobox(
            options_frame, textvariable=self.lang_var, width=14, state='readonly',
            values=[label for _, label in LANGUAGES])
        self.lang_combo.grid(row=2, column=1, sticky='w', padx=4, pady=(10, 0))

        ttk.Label(options_frame, text='Motor de voz:').grid(row=3, column=0, sticky='w', pady=(6, 0))
        default_tts_label = TTS_ENGINES[0][1]
        self.tts_engine_var = tk.StringVar(value=default_tts_label)
        self.tts_engine_combo = ttk.Combobox(
            options_frame, textvariable=self.tts_engine_var, width=14, state='readonly',
            values=[label for _, label in TTS_ENGINES])
        self.tts_engine_combo.grid(row=3, column=1, sticky='w', padx=4, pady=(6, 0))

        options_frame.columnconfigure(0, weight=1)
        options_frame.columnconfigure(1, weight=1)

        hint = ('Configure este mesmo dispositivo como "microfone" dentro do app de chamada '
                '(Zoom/Meet/Teams) para que as outras pessoas ouçam a fala — você não vai ouvir '
                'nada aqui, o áudio só sai por esse dispositivo virtual.')
        ttk.Label(self, text=hint, wraplength=600, foreground='#666').pack(fill='x', padx=10, pady=(0, 4))

        self.text_box = scrolledtext.ScrolledText(self, height=10, wrap='word')
        self.text_box.pack(fill='both', expand=True, padx=10, pady=(4, 10))

        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill='x', padx=10, pady=(0, 10))
        self.status_var = tk.StringVar(value='Ocioso')
        ttk.Label(bottom_frame, textvariable=self.status_var).pack(side='left')
        self.speak_button = ttk.Button(bottom_frame, text=LABEL_IDLE, command=self._on_speak)
        self.speak_button.pack(side='right')

    def _refresh_devices(self):
        previous = self.device_var.get()
        devices = sd.query_devices()
        self._output_devices = [
            (i, d['name']) for i, d in enumerate(devices) if d.get('max_output_channels', 0) > 0
        ]
        labels = [f'{i}: {name}' for i, name in self._output_devices]
        self.device_combo.configure(values=labels)
        if previous in labels:
            self.device_var.set(previous)
        else:
            # Padrão: um driver de loopback (ex.: BlackHole), que é o
            # cenário de uso desta aba — evita tocar sem querer nos
            # alto-falantes de verdade.
            loopback = next((label for label in labels if 'blackhole' in label.lower()), None)
            self.device_var.set(loopback or (labels[0] if labels else ''))

    def _selected_device_index(self):
        label = self.device_var.get()
        if not label:
            return None
        return int(label.split(':', 1)[0])

    def _selected_lang_code(self):
        label = self.lang_var.get()
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

    def _set_status(self, status):
        self._event_queue.put(('status', status))

    def _finish(self):
        self._event_queue.put(('finish', None))

    # -- processamento da fila, executado só na thread principal -------------

    def _drain_queue(self):
        while True:
            try:
                kind, payload = self._event_queue.get_nowait()
            except queue.Empty:
                break

            if kind == 'status':
                self.status_var.set(payload)
            elif kind == 'finish':
                self._speaking = False
                self._sync_controls()

        self.after(100, self._drain_queue)

    def _sync_controls(self):
        if self._speaking:
            self.speak_button.configure(text=LABEL_SPEAKING, state='disabled')
            self.device_combo.configure(state='disabled')
            self.refresh_devices_button.configure(state='disabled')
            self.lang_combo.configure(state='disabled')
            self.tts_engine_combo.configure(state='disabled')
        else:
            self.speak_button.configure(text=LABEL_IDLE, state='normal')
            self.device_combo.configure(state='readonly')
            self.refresh_devices_button.configure(state='normal')
            self.lang_combo.configure(state='readonly')
            self.tts_engine_combo.configure(state='readonly')

    def _on_speak(self):
        if self._speaking:
            return
        text = self.text_box.get('1.0', 'end').strip()
        if not text:
            return
        device = self._selected_device_index()
        if device is None:
            self._set_status('Nenhum dispositivo de saída disponível.')
            return

        lang = self._selected_lang_code()
        engine = self._selected_tts_engine()

        self._speaking = True
        self._sync_controls()
        threading.Thread(target=self._speak_worker, args=(text, lang, device, engine), daemon=True).start()

    def _speak_worker(self, text, lang, device, engine):
        try:
            self._set_status('Sintetizando e reproduzindo...')
            speak_to_device(text, lang, device=device, engine=engine)
            self._set_status('Ocioso')
        except Exception as exc:
            self._set_status(f'Erro: {exc}')
        finally:
            self._finish()

    def shutdown(self):
        """Nada para sinalizar: a fala em andamento (se houver) termina sozinha; a thread é daemon."""
