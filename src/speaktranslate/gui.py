import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

import numpy as np

from app_constants import LANGUAGES, TTS_ENGINES, WHISPER_MODELS
from audio_capture import ContinuousAudioCapture, list_input_devices
from stream_transcription import LocalAgreementTranscriber
from streaming_gui import StreamingTranslationTab
from suggest_panel import SuggestReplyPanel
from transcription import create_model
from translation import translate
from tts import speak
from interview_gui import InterviewTab
from virtual_mic_gui import VirtualMicTab

SAMPLE_RATE = 16000
DEFAULT_MODEL = 'base'
DEFAULT_TARGET_LANG = 'pt'
PROCESS_INTERVAL_S = 0.5  # intervalo entre passagens de re-transcrição

AUTO_DETECT_LABEL = 'Detectar automaticamente'

# Um clique inicia a captura contínua; o próximo encerra — a frase pendente
# e a fala já enfileirada terminam antes de o app voltar a ficar pronto.
LABEL_IDLE = '🎙 Iniciar Transcrição'
LABEL_RUNNING = '⏹ Parar Transcrição'
LABEL_STOPPING = 'Finalizando...'


class InitialTranslationTab(ttk.Frame):
    """
    Aba "Tradução Inicial": captura contínua do microfone (toggle
    iniciar/parar), transcreve, traduz e fala o resultado. Usa a mesma
    re-transcrição incremental da aba "Tradução por Streaming" (ver
    stream_transcription.py): uma pausa na fala só fecha a frase atual — a
    captura segue ativa até clicar em "Parar".

    Cada frase fechada é traduzida, mostrada e (se "Reproduzir áudio" estiver
    marcado) enfileirada para a voz numa thread separada — exceto quando a
    frase já está no idioma de destino (nada a traduzir, ler em voz alta não
    ajuda). A captura NÃO para enquanto a voz toca (pensado para uso com
    fone de ouvido); com alto-falantes, marque "Pausar microfone durante a
    voz" para a fala sintetizada não ser captada de volta — ao custo de
    perder o que for dito enquanto ela toca.

    O painel "Sugerir resposta" (suggest_panel.py) recebe cada frase fechada.
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

        # 'idle' | 'running' | 'stopping'
        self._state = 'idle'
        self._stop_event = threading.Event()
        self._speaking = threading.Event()
        self._worker_thread = None
        self._input_devices = []
        self._last_preview_text = ''

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

        # Idioma de quem fala. "Detectar automaticamente" serve para conversas
        # que alternam idiomas; fixar o idioma deixa a transcrição mais rápida
        # e evita erros de detecção em trechos curtos (ver
        # stream_transcription.py).
        ttk.Label(frame, text='Origem:').grid(row=0, column=0, sticky='w')
        self.source_lang_var = tk.StringVar(value=AUTO_DETECT_LABEL)
        self.source_lang_combo = ttk.Combobox(
            frame, textvariable=self.source_lang_var, width=16, state='readonly',
            values=[AUTO_DETECT_LABEL] + [label for _, label in LANGUAGES])
        self.source_lang_combo.grid(row=0, column=1, sticky='w', padx=(4, 14))

        ttk.Label(frame, text='Destino:').grid(row=0, column=2, sticky='w')
        default_label = next(
            (label for code, label in LANGUAGES if code == DEFAULT_TARGET_LANG), LANGUAGES[0][1])
        self.target_lang_var = tk.StringVar(value=default_label)
        self.target_lang_entry = ttk.Combobox(
            frame, textvariable=self.target_lang_var, width=12, state='readonly',
            values=[label for _, label in LANGUAGES])
        self.target_lang_entry.grid(row=0, column=3, sticky='w', padx=(4, 14))

        ttk.Label(frame, text='Modelo:').grid(row=0, column=4, sticky='w')
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.model_combo = ttk.Combobox(frame, textvariable=self.model_var, width=8,
                                         values=WHISPER_MODELS, state='readonly')
        self.model_combo.grid(row=0, column=5, sticky='w', padx=4)

        ttk.Label(frame, text='Voz:').grid(row=1, column=0, sticky='w', pady=(6, 0))
        default_tts_label = TTS_ENGINES[0][1]
        self.tts_engine_var = tk.StringVar(value=default_tts_label)
        self.tts_engine_combo = ttk.Combobox(
            frame, textvariable=self.tts_engine_var, width=12, state='readonly',
            values=[label for _, label in TTS_ENGINES])
        self.tts_engine_combo.grid(row=1, column=1, sticky='w', padx=(4, 14), pady=(6, 0))

        # Ligado por padrão (comportamento de sempre); desmarcar pula a
        # etapa de síntese/reprodução — útil pra quem só quer ver o texto
        # transcrito/traduzido, sem a fala em voz alta (e sem descartar o
        # áudio do microfone enquanto a voz toca).
        self.play_audio_var = tk.BooleanVar(value=True)
        self.play_audio_check = ttk.Checkbutton(frame, text='Reproduzir áudio', variable=self.play_audio_var)
        self.play_audio_check.grid(row=1, column=2, sticky='w', pady=(6, 0))

        # Desligado por padrão: com fone de ouvido não há eco, e pausar faria
        # perder tudo o que for dito enquanto a voz toca.
        self.pause_mic_var = tk.BooleanVar(value=False)
        self.pause_mic_check = ttk.Checkbutton(
            frame, text='Pausar microfone durante a voz (sem fone)', variable=self.pause_mic_var)
        self.pause_mic_check.grid(row=1, column=3, columnspan=3, sticky='w', padx=(10, 0), pady=(6, 0))

        ttk.Label(frame, text='Entrada:').grid(row=2, column=0, sticky='w', pady=(6, 0))
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(frame, textvariable=self.device_var, width=32, state='readonly')
        self.device_combo.grid(row=2, column=1, columnspan=3, sticky='we', padx=(4, 4), pady=(6, 0))
        self.refresh_devices_button = ttk.Button(frame, text='⟳', width=3, command=self._refresh_devices)
        self.refresh_devices_button.grid(row=2, column=4, sticky='w', pady=(6, 0))

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
        aba de streaming, inclusive a linha provisória em itálico."""
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
            transcript_frame, height=12, state='disabled', wrap='word', font=('TkDefaultFont', 12))
        self.transcript_text.pack(fill='both', expand=True)
        panes.add(transcript_frame, weight=1)

        translation_frame = ttk.Frame(panes)
        ttk.Label(translation_frame, text='Tradução', font=('TkDefaultFont', 11, 'bold')).pack(anchor='w')
        self.preview_translation_var = tk.StringVar(value='')
        ttk.Label(translation_frame, textvariable=self.preview_translation_var, **preview_kwargs).pack(
            fill='x', pady=(0, 4))
        self.translation_text = scrolledtext.ScrolledText(
            translation_frame, height=12, state='disabled', wrap='word', font=('TkDefaultFont', 12))
        self.translation_text.pack(fill='both', expand=True)
        panes.add(translation_frame, weight=1)

    def _build_suggest_block(self):
        """Botão "Sugerir resposta": mesmo painel da aba de streaming (ver
        suggest_panel.py), alimentado com cada frase fechada."""
        self.suggest_panel = SuggestReplyPanel(self)
        self.suggest_panel.pack(fill='x', padx=10, pady=(0, 10))

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

    def _set_preview(self, text):
        self._event_queue.put(('preview', text))

    def _set_preview_translation(self, text):
        self._event_queue.put(('preview_translation', text))

    def _add_suggest_block(self, text, lang):
        self._event_queue.put(('suggest_block', (text, lang)))

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
            elif kind == 'preview_translation':
                self.preview_translation_var.set(payload)
            elif kind == 'suggest_block':
                self.suggest_panel.add_block(*payload)
            elif kind == 'finish':
                self._state = 'idle'
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
        if self._state == 'idle':
            self._stop_event = threading.Event()
            self._state = 'running'
            self._sync_controls()
            self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._worker_thread.start()
        elif self._state == 'running':
            # Só sinaliza o fim da captura; a frase pendente e a fala já
            # enfileirada terminam antes de a worker thread avisar "finish".
            self._stop_event.set()
            self._state = 'stopping'
            self._sync_controls()
        # em 'stopping' o botão fica desabilitado; clique é ignorado.

    def _sync_controls(self):
        if self._state == 'idle':
            self.toggle_button.configure(text=LABEL_IDLE, state='normal')
            self.model_combo.configure(state='readonly')
            self.source_lang_combo.configure(state='readonly')
            self.device_combo.configure(state='readonly')
            self.refresh_devices_button.configure(state='normal')
            self.target_lang_entry.configure(state='readonly')
            self.tts_engine_combo.configure(state='readonly')
            self.play_audio_check.configure(state='normal')
            self.pause_mic_check.configure(state='normal')
        elif self._state == 'running':
            self.toggle_button.configure(text=LABEL_RUNNING, state='normal')
            self.model_combo.configure(state='disabled')
            self.source_lang_combo.configure(state='disabled')
            self.device_combo.configure(state='disabled')
            self.refresh_devices_button.configure(state='disabled')
            self.target_lang_entry.configure(state='disabled')
            self.tts_engine_combo.configure(state='disabled')
            self.play_audio_check.configure(state='disabled')
            self.pause_mic_check.configure(state='disabled')
        else:  # stopping
            self.toggle_button.configure(text=LABEL_STOPPING, state='disabled')

    def shutdown(self):
        """Sinaliza para a worker thread encerrar; não bloqueia a saída do app."""
        self._stop_event.set()

    def _run_loop(self):
        source_lang = self._selected_source_lang_code()
        target_lang = self._selected_target_lang_code()
        model_size = self.model_var.get()
        device = self._selected_device_index()
        tts_engine = self._selected_tts_engine()
        play_audio = self.play_audio_var.get()
        pause_mic = play_audio and self.pause_mic_var.get()

        capture = None
        tts_queue = None
        tts_thread = None
        try:
            if self.model is None or self._loaded_model_size != model_size:
                self._set_status('Carregando modelo...')
                self.model = create_model(model_size=model_size, device='auto')
                self._loaded_model_size = model_size

            if play_audio:
                tts_queue = queue.Queue()
                tts_thread = threading.Thread(
                    target=self._tts_worker, args=(tts_queue, tts_engine), daemon=True)
                tts_thread.start()

            engine = LocalAgreementTranscriber(self.model, sample_rate=SAMPLE_RATE, language=source_lang)
            last_detected_lang = source_lang or 'en'
            self._last_preview_text = ''
            self._speaking.clear()

            self._set_status('Ouvindo...')
            capture = ContinuousAudioCapture(sample_rate=SAMPLE_RATE, device=device)
            capture.start()

            mic_paused = False
            while not self._stop_event.is_set():
                self._stop_event.wait(PROCESS_INTERVAL_S)
                audio_chunk = capture.read_available()
                if pause_mic and self._speaking.is_set():
                    # Descarta o eco da própria voz (ver docstring da classe).
                    # Na entrada da pausa, um trecho de silêncio fecha a frase
                    # em andamento — sem isso, a fala de antes e a de depois
                    # da pausa seriam coladas num áudio só, sem sentido.
                    if not mic_paused:
                        mic_paused = True
                        engine.feed(np.zeros(int(1.5 * SAMPLE_RATE), dtype=np.int16))
                        self._process_once(engine, target_lang, tts_queue)
                    continue
                mic_paused = False
                engine.feed(audio_chunk)
                detected = self._process_once(engine, target_lang, tts_queue)
                if detected:
                    last_detected_lang = detected

            # dreno final: processa o que restou no buffer e fecha a frase pendente
            audio_chunk = capture.read_available()
            if not (pause_mic and self._speaking.is_set()):
                engine.feed(audio_chunk)
            detected = self._process_once(engine, target_lang, tts_queue)
            last_detected_lang = detected or last_detected_lang
            final_sentence = engine.flush()
            if final_sentence:
                self._translate_and_show(final_sentence, last_detected_lang, target_lang, tts_queue)

            self._set_preview('')
            self._set_preview_translation('')

            # Deixa a voz terminar o que já foi enfileirado, em vez de cortar
            # a fala no meio.
            if tts_queue is not None:
                if not tts_queue.empty() or self._speaking.is_set():
                    self._set_status('Finalizando fala...')
                tts_queue.put(None)
                tts_thread.join(timeout=60)
                tts_queue = None
        except Exception as exc:
            self._append_transcript(f'\n[Erro: {exc}]')
        finally:
            if capture is not None:
                capture.stop()
            if tts_queue is not None:
                tts_queue.put(None)
            self._set_status('')
            self._finish()

    def _tts_worker(self, tts_queue, tts_engine):
        """Fala as frases traduzidas numa thread separada, para que a
        captura/transcrição nunca fique bloqueada esperando o áudio
        terminar. Marca `_speaking` enquanto toca, para o loop principal
        poder pausar o microfone nesse intervalo (se a opção estiver marcada)."""
        while True:
            item = tts_queue.get()
            if item is None:
                self._speaking.clear()
                return
            text, lang = item
            self._speaking.set()
            try:
                speak(text, lang, engine=tts_engine)
            except Exception as exc:
                self._append_transcript(f'\n[erro ao falar: {exc}]')
            finally:
                if tts_queue.empty():
                    self._speaking.clear()

    def _process_once(self, engine, target_lang, tts_queue):
        """Roda uma passagem de re-transcrição. Retorna o idioma detectado, se houve passagem."""
        if not engine.has_pending_audio():
            return None
        result = engine.process()
        if result['committed']:
            self._append_transcript(result['committed'])
        self._set_preview(result['preview'])

        if result['sentence']:
            self._set_preview_translation('')
            self._translate_and_show(result['sentence'], result['language'], target_lang, tts_queue)
        else:
            self._update_preview_translation(result['preview'], result['language'], target_lang)

        return result['language']

    def _update_preview_translation(self, preview_text, source_lang, target_lang):
        preview_text = preview_text.strip()
        if preview_text == self._last_preview_text:
            return
        self._last_preview_text = preview_text
        # Origem = destino: nada a traduzir (só a transcrição importa).
        if not preview_text or source_lang == target_lang:
            self._set_preview_translation('')
            return
        try:
            translated = translate(preview_text, source_lang, target_lang)
        except Exception:
            return  # falha na tradução provisória não é grave; a próxima passagem tenta de novo
        self._set_preview_translation(translated)

    def _translate_and_show(self, sentence, source_lang, target_lang, tts_queue):
        sentence = sentence.strip()
        if not sentence:
            return
        # Frase fechada, no idioma original, vai para o campo "Conversa" do
        # painel "Sugerir resposta".
        self._add_suggest_block(sentence, source_lang)
        if source_lang == target_lang:
            return  # já está no idioma de destino: fica só na transcrição
        try:
            translated = translate(sentence, source_lang, target_lang)
        except Exception as exc:
            self._append_translation(f'[erro na tradução: {exc}]')
            return
        self._append_translation(translated)
        if tts_queue is not None:
            tts_queue.put((translated, target_lang))


class App:
    def __init__(self, root):
        self.root = root
        self.root.title('SpeakTranslate')
        self.root.geometry('640x560')
        self.root.minsize(760, 720)

        notebook = ttk.Notebook(root)
        notebook.pack(fill='both', expand=True)

        self.initial_tab = InitialTranslationTab(notebook)
        notebook.add(self.initial_tab, text='Tradução Inicial')

        self.streaming_tab = StreamingTranslationTab(notebook)
        notebook.add(self.streaming_tab, text='Tradução por Streaming')

        self.virtual_mic_tab = VirtualMicTab(notebook)
        notebook.add(self.virtual_mic_tab, text='Microfone Virtual')

        self.interview_tab = InterviewTab(notebook)
        notebook.add(self.interview_tab, text='Entrevista')

        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    def _on_close(self):
        self.initial_tab.shutdown()
        self.streaming_tab.shutdown()
        self.virtual_mic_tab.shutdown()
        self.interview_tab.shutdown()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
