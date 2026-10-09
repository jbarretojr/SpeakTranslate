import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

from env_config import load_dotenv_once
from obs_controller import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    OBSConnectionError,
    connect,
    set_video_file,
    start_virtual_cam,
    stop_virtual_cam,
)

LABEL_IDLE = '🎥 Iniciar Câmera Virtual'
LABEL_RUNNING = '⏹ Parar Câmera Virtual'
LABEL_BUSY = 'Aguarde...'

VIDEO_FILETYPES = [
    ('Vídeos', '*.mp4 *.mov *.m4v *.mkv *.avi *.webm'),
    ('Todos os arquivos', '*.*'),
]


class InterviewTab(ttk.Frame):
    """
    Aba "Entrevista": escolhe um arquivo de vídeo e transmite ele em loop
    contínuo como câmera virtual do macOS, pra qualquer app (Chrome, Zoom,
    Meet, FaceTime...) selecionar como se fosse uma webcam normal.

    Não implementa a câmera virtual em si — controla um OBS Studio já
    instalado via obs-websocket (ver obs_controller.py, com a análise
    completa de por que essa é a abordagem recomendada hoje no macOS em vez
    de uma Camera Extension própria). Esta aba só cuida de: escolher o
    vídeo, criar/atualizar a Fonte de Mídia correspondente no OBS, e
    ligar/desligar a "OBS Virtual Camera".
    """

    def __init__(self, master):
        super().__init__(master, padding=0)

        self._event_queue = queue.Queue()
        self._running = False
        self._busy = False
        self._client = None  # conexão com o OBS, reaproveitada entre ações

        self._build_widgets()
        self.after(100, self._drain_queue)

    def _build_widgets(self):
        # Pré-preenche host/porta/senha a partir de variáveis de ambiente
        # (OBS_WEBSOCKET_HOST/PORT/PASSWORD), se definidas — ex.: num .env na
        # raiz do projeto (ver .env.example), pra não precisar redigitar a
        # senha a cada vez que o app abre. Os campos continuam editáveis.
        load_dotenv_once()
        # `or` em vez de `os.environ.get(key, default)`: no .env.example as
        # variáveis existem vazias (""), e .get() com default só entra em
        # ação se a CHAVE não existir — precisamos tratar "existe mas vazia"
        # como "não configurada" também.
        default_host = os.environ.get('OBS_WEBSOCKET_HOST') or DEFAULT_HOST
        default_port = os.environ.get('OBS_WEBSOCKET_PORT') or str(DEFAULT_PORT)
        default_password = os.environ.get('OBS_WEBSOCKET_PASSWORD') or ''

        conn_frame = ttk.Frame(self, padding=(10, 10, 10, 4))
        conn_frame.pack(fill='x')

        ttk.Label(conn_frame, text='Host:').grid(row=0, column=0, sticky='w')
        self.host_var = tk.StringVar(value=default_host)
        ttk.Entry(conn_frame, textvariable=self.host_var, width=14).grid(
            row=0, column=1, sticky='w', padx=(4, 14))

        ttk.Label(conn_frame, text='Porta:').grid(row=0, column=2, sticky='w')
        self.port_var = tk.StringVar(value=default_port)
        ttk.Entry(conn_frame, textvariable=self.port_var, width=8).grid(
            row=0, column=3, sticky='w', padx=(4, 14))

        ttk.Label(conn_frame, text='Senha do WebSocket:').grid(row=0, column=4, sticky='w')
        self.password_var = tk.StringVar(value=default_password)
        ttk.Entry(conn_frame, textvariable=self.password_var, width=20, show='•').grid(
            row=0, column=5, sticky='w', padx=4)

        video_frame = ttk.Frame(self, padding=(10, 6, 10, 4))
        video_frame.pack(fill='x')

        ttk.Label(video_frame, text='Vídeo:').pack(side='left')
        self.video_path_var = tk.StringVar(value='')
        ttk.Entry(video_frame, textvariable=self.video_path_var, state='readonly').pack(
            side='left', fill='x', expand=True, padx=(4, 8))
        self.choose_button = ttk.Button(video_frame, text='Escolher...', command=self._on_choose_video)
        self.choose_button.pack(side='left')

        control_frame = ttk.Frame(self, padding=(10, 4, 10, 4))
        control_frame.pack(fill='x')
        self.toggle_button = ttk.Button(control_frame, text=LABEL_IDLE, command=self._on_toggle)
        self.toggle_button.pack(side='left')
        self.status_var = tk.StringVar(value='')
        ttk.Label(control_frame, textvariable=self.status_var, font=('TkDefaultFont', 11, 'bold')).pack(
            side='left', padx=(10, 0))

        hint = ('Pré-requisitos: OBS Studio instalado e ABERTO (brew install --cask obs) — sem o OBS '
                'rodando, a conexão falha com "connection refused". Habilite o servidor WebSocket em '
                'Ferramentas > WebSocket Server Settings (vem DESLIGADO por padrão, mesmo em instalações '
                'novas) e copie a senha de lá ("Show Connect Info") pro campo acima — sem ela, a conexão '
                'falha com "authentication enabled but no password provided". Dica: salve a senha em '
                'OBS_WEBSOCKET_PASSWORD no .env (ver .env.example) pra não precisar redigitar a cada vez. '
                'Na primeira vez que a câmera virtual for ligada, o macOS pede aprovação manual da extensão '
                'do OBS em Ajustes > Privacidade e Segurança; depois disso não pede mais. O vídeo escolhido '
                'aparece no Chrome/Zoom/Meet como a webcam "OBS Virtual Camera", em loop contínuo, até '
                'clicar em "Parar".')
        ttk.Label(self, text=hint, wraplength=700, foreground='#888').pack(
            fill='x', padx=10, pady=(0, 6))

        self.log_text = scrolledtext.ScrolledText(self, height=10, state='disabled', wrap='word')
        self.log_text.pack(fill='both', expand=True, padx=10, pady=(0, 10))

    # -- chamadas seguras a partir da worker thread: só enfileiram -----------

    def _set_status(self, status):
        self._event_queue.put(('status', status))

    def _log(self, message):
        self._event_queue.put(('log', message))

    def _finish(self, running):
        self._event_queue.put(('finish', running))

    # -- processamento da fila, executado só na thread principal -------------

    def _drain_queue(self):
        while True:
            try:
                kind, payload = self._event_queue.get_nowait()
            except queue.Empty:
                break

            if kind == 'status':
                self.status_var.set(payload)
            elif kind == 'log':
                self.log_text.configure(state='normal')
                self.log_text.insert('end', payload + '\n')
                self.log_text.see('end')
                self.log_text.configure(state='disabled')
            elif kind == 'finish':
                self._busy = False
                self._running = payload
                self._sync_controls()

        self.after(100, self._drain_queue)

    def _sync_controls(self):
        if self._busy:
            self.toggle_button.configure(text=LABEL_BUSY, state='disabled')
            self.choose_button.configure(state='disabled')
        elif self._running:
            self.toggle_button.configure(text=LABEL_RUNNING, state='normal')
            self.choose_button.configure(state='disabled')
        else:
            self.toggle_button.configure(text=LABEL_IDLE, state='normal')
            self.choose_button.configure(state='normal')

    def _on_choose_video(self):
        path = filedialog.askopenfilename(title='Escolha um arquivo de vídeo', filetypes=VIDEO_FILETYPES)
        if path:
            self.video_path_var.set(path)

    def _selected_connection(self):
        host = self.host_var.get().strip() or DEFAULT_HOST
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            port = DEFAULT_PORT
        password = self.password_var.get()
        return host, port, password

    def _on_toggle(self):
        if self._busy:
            return

        if not self._running:
            video_path = self.video_path_var.get()
            if not video_path:
                self._log('[Escolha um arquivo de vídeo antes de iniciar.]')
                return
            self._busy = True
            self._sync_controls()
            host, port, password = self._selected_connection()
            threading.Thread(
                target=self._start_worker, args=(host, port, password, video_path), daemon=True).start()
        else:
            self._busy = True
            self._sync_controls()
            threading.Thread(target=self._stop_worker, daemon=True).start()

    def _start_worker(self, host, port, password, video_path):
        try:
            self._set_status('Conectando ao OBS...')
            self._client = connect(host=host, port=port, password=password)

            self._set_status('Configurando o vídeo no OBS...')
            set_video_file(self._client, video_path)

            self._set_status('Ligando a câmera virtual...')
            start_virtual_cam(self._client)

            self._log(f'Câmera virtual ativa, transmitindo "{video_path}" em loop.')
            self._set_status('Câmera virtual ativa ✅')
            self._finish(True)
        except OBSConnectionError as exc:
            self._log(f'[Erro: {exc}]')
            self._set_status('Erro ao conectar')
            self._finish(False)
        except Exception as exc:
            self._log(f'[Erro: {exc}]')
            self._set_status('Erro')
            self._finish(False)

    def _stop_worker(self):
        try:
            self._set_status('Parando a câmera virtual...')
            if self._client is not None:
                stop_virtual_cam(self._client)
            self._log('Câmera virtual parada.')
            self._set_status('')
            self._finish(False)
        except Exception as exc:
            self._log(f'[Erro ao parar: {exc}]')
            self._set_status('Erro')
            # Mesmo com erro ao avisar o OBS, o estado local volta pra
            # "parado" — o usuário pode conferir/parar direto no OBS se
            # necessário.
            self._finish(False)

    def shutdown(self):
        """Não para a câmera virtual automaticamente ao fechar o app — ela
        continua ativa no OBS (útil se a entrevista/chamada ainda estiver
        rolando); só libera a conexão com o WebSocket."""
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
