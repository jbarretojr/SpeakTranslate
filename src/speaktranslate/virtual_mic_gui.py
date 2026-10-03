import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

import sounddevice as sd

from app_constants import LANGUAGES, TTS_ENGINES
from lang_detect import detect_language
from translation import translate
from tts import kokoro_voices_for_lang, speak_to_device

DEFAULT_TARGET_LANG = 'en'

LABEL_IDLE = '🔊 Falar no microfone virtual'
LABEL_SPEAKING = 'Falando...'


class VirtualMicTab(ttk.Frame):
    """
    Aba "Microfone Virtual": digite um texto, escolha o idioma de saída e
    toque a fala sintetizada num dispositivo de áudio virtual (ex.: BlackHole)
    em vez do dispositivo de saída padrão — quem está numa chamada com esse
    dispositivo configurado como microfone escuta; você não.

    Antes de falar, detecta automaticamente o idioma do texto digitado (ver
    lang_detect.py): se já estiver no idioma de saída escolhido, fala direto;
    se estiver em outro idioma, traduz primeiro (translation.py, local) e
    fala o resultado — não precisa trocar o idioma de saída manualmente nem
    traduzir o texto você mesmo antes de colar aqui.

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
        self._sync_kokoro_voice_options()
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
        self.lang_combo.bind('<<ComboboxSelected>>', lambda _event: self._sync_kokoro_voice_options())

        ttk.Label(options_frame, text='Motor de voz:').grid(row=3, column=0, sticky='w', pady=(6, 0))
        default_tts_label = TTS_ENGINES[0][1]
        self.tts_engine_var = tk.StringVar(value=default_tts_label)
        self.tts_engine_combo = ttk.Combobox(
            options_frame, textvariable=self.tts_engine_var, width=14, state='readonly',
            values=[label for _, label in TTS_ENGINES])
        self.tts_engine_combo.grid(row=3, column=1, sticky='w', padx=4, pady=(6, 0))
        self.tts_engine_combo.bind('<<ComboboxSelected>>', lambda _event: self._sync_kokoro_voice_options())

        # Só tem efeito (e só fica habilitado) quando o motor "Kokoro" está
        # selecionado — os outros motores já escolhem a própria voz por
        # idioma. Lista de vozes refeita a cada troca de idioma/motor.
        ttk.Label(options_frame, text='Voz Kokoro:').grid(row=4, column=0, sticky='w', pady=(6, 0))
        self.kokoro_voice_var = tk.StringVar(value='')
        self.kokoro_voice_combo = ttk.Combobox(
            options_frame, textvariable=self.kokoro_voice_var, width=14, state='disabled')
        self.kokoro_voice_combo.grid(row=4, column=1, sticky='w', padx=4, pady=(6, 0))

        options_frame.columnconfigure(0, weight=1)
        options_frame.columnconfigure(1, weight=1)

        hint = ('Configure este mesmo dispositivo como "microfone" dentro do app de chamada '
                '(Zoom/Meet/Teams) para que as outras pessoas ouçam a fala — você não vai ouvir '
                'nada aqui, o áudio só sai por esse dispositivo virtual.')
        ttk.Label(self, text=hint, wraplength=600, foreground='#666').pack(fill='x', padx=10, pady=(0, 4))

        self.text_box = scrolledtext.ScrolledText(self, height=10, wrap='word')
        self.text_box.pack(fill='both', expand=True, padx=10, pady=(4, 4))

        # Mostra o resultado da detecção de idioma/tradução automática antes
        # de falar — assim dá pra conferir o que vai ser dito de fato, já que
        # o texto digitado pode não ser o que sai pelo dispositivo virtual.
        self.translation_preview_var = tk.StringVar(value='')
        ttk.Label(self, textvariable=self.translation_preview_var, foreground='#888',
                  font=('TkDefaultFont', 10, 'italic'), wraplength=600, justify='left', anchor='w').pack(
            fill='x', padx=10, pady=(0, 6))

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

    def _selected_kokoro_voice(self):
        """None quando o motor não é "kokoro" ou quando não há voz escolhida
        — nesse caso `speak_to_device()` usa a voz padrão do idioma."""
        return self.kokoro_voice_var.get() or None

    def _sync_kokoro_voice_options(self):
        """Refaz a lista de vozes do combobox "Voz Kokoro:" a partir do
        idioma/motor selecionados no momento. Chamado na troca de idioma, na
        troca de motor, e por `_sync_controls()` (que também cuida de
        habilitar/desabilitar durante a fala)."""
        engine = self._selected_tts_engine()
        lang = self._selected_lang_code()
        voices = kokoro_voices_for_lang(lang) if engine == 'kokoro' else []

        previous = self.kokoro_voice_var.get()
        self.kokoro_voice_combo.configure(values=voices)
        if not voices:
            self.kokoro_voice_combo.configure(state='disabled')
            self.kokoro_voice_var.set('')
            return

        self.kokoro_voice_combo.configure(state='disabled' if self._speaking else 'readonly')
        self.kokoro_voice_var.set(previous if previous in voices else voices[0])

    # -- chamadas seguras a partir da worker thread: só enfileiram -----------

    def _set_status(self, status):
        self._event_queue.put(('status', status))

    def _set_translation_preview(self, text):
        self._event_queue.put(('translation_preview', text))

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
            elif kind == 'translation_preview':
                self.translation_preview_var.set(payload)
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
        self._sync_kokoro_voice_options()

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
        voice = self._selected_kokoro_voice()

        self._speaking = True
        self._sync_controls()
        self._set_translation_preview('')
        threading.Thread(
            target=self._speak_worker, args=(text, lang, device, engine, voice), daemon=True).start()

    def _speak_worker(self, text, lang, device, engine, voice):
        try:
            self._set_status('Detectando idioma do texto...')
            detected_lang = detect_language(text)

            speak_text = text
            if detected_lang and detected_lang != lang:
                # Texto digitado em outro idioma: traduz pro idioma de saída
                # antes de falar, em vez de falar o texto original sem
                # querer no idioma errado.
                self._set_status(f'Traduzindo de "{detected_lang}" para "{lang}"...')
                speak_text = translate(text, detected_lang, lang)
                self._set_translation_preview(f'Traduzido ({detected_lang} → {lang}): {speak_text}')
            else:
                self._set_translation_preview('Texto já está no idioma de saída — falando sem traduzir.')

            self._set_status('Sintetizando e reproduzindo...')
            speak_to_device(speak_text, lang, device=device, engine=engine, voice=voice)
            self._set_status('Ocioso')
        except Exception as exc:
            self._set_status(f'Erro: {exc}')
        finally:
            self._finish()

    def shutdown(self):
        """Nada para sinalizar: a fala em andamento (se houver) termina sozinha; a thread é daemon."""
