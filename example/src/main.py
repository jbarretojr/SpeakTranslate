import os
import sys
import time
from pynput.keyboard import Controller
from PyQt5.QtCore import QObject, QProcess
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction, QMessageBox

from key_listener import KeyListener
from result_thread import ResultThread
from ui.main_window import MainWindow
from ui.settings_window import SettingsWindow
from ui.status_window import StatusWindow
from ui.text_transforms_window import TextTransformsWindow
from transcription import create_local_model
from input_simulation import InputSimulator
from text_processing import ProcessedTranscription
from utils import ASSETS_DIR, ConfigManager, play_sound

ROOT = os.environ.get('VOICENOTE_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(ROOT, 'src')


class VoiceNoteApp(QObject):
    def __init__(self):
        """Inicializa a aplicação, abrindo a janela de configurações se não houver arquivo de configuração."""
        super().__init__()
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setWindowIcon(QIcon(os.path.join(ASSETS_DIR, 'logo.png')))

        ConfigManager.initialize()

        self.key_listener = None
        self.input_simulator = None
        self.result_thread = None

        self.settings_window = SettingsWindow()
        self.settings_window.settings_closed.connect(self.on_settings_closed)
        self.settings_window.settings_saved.connect(self.restart_app)
        self.settings_window.openTextTransforms.connect(self.show_text_transforms)

        self.text_transforms_window = TextTransformsWindow()

        if ConfigManager.config_file_exists():
            self.initialize_components()
        else:
            print('Nenhum arquivo de configuração válido encontrado. Abrindo janela de configurações...')
            self.settings_window.show()

    def initialize_components(self):
        """Inicializa os componentes da aplicação."""
        self.input_simulator = InputSimulator()

        self.key_listener = KeyListener()
        self.key_listener.add_callback("on_activate", self.on_activation)
        self.key_listener.add_callback("on_deactivate", self.on_deactivation)
        activation_key = ConfigManager.get_config_value('recording_options', 'activation_key')
        ConfigManager.console_print(f'Atalho de ativação: {activation_key}')

        model_options = ConfigManager.get_config_section('model_options')
        self.local_model = create_local_model() if not model_options.get('use_api') else None

        self.result_thread = None

        self.main_window = MainWindow()
        self.main_window.openSettings.connect(self.settings_window.show)
        self.main_window.openTextTransforms.connect(self.show_text_transforms)
        self.main_window.startListening.connect(self.key_listener.start)
        self.main_window.closeApp.connect(self.exit_app)

        if not ConfigManager.get_config_value('misc', 'hide_status_window'):
            self.status_window = StatusWindow()

        self.create_tray_icon()
        self.main_window.show()

    def create_tray_icon(self):
        """Cria o ícone da bandeja do sistema e seu menu de contexto."""
        icon_path = os.path.join(ASSETS_DIR, 'logo.png')
        icon = QIcon(icon_path)
        if icon.isNull():
            ConfigManager.console_print(f'Ícone da bandeja não encontrado: {icon_path}')
            return

        if not QSystemTrayIcon.isSystemTrayAvailable():
            ConfigManager.console_print(
                'Bandeja do sistema indisponível. No GNOME, instale a extensão '
                'AppIndicator (gnome-shell-extension-appindicator) e reinicie a sessão.'
            )
            return

        self.tray_icon = QSystemTrayIcon(icon, self.app)
        self.tray_icon.setToolTip('VoiceNote')

        tray_menu = QMenu()

        show_action = QAction('Menu principal do VoiceNote', self.app)
        show_action.triggered.connect(self.main_window.show)
        tray_menu.addAction(show_action)

        settings_action = QAction('Abrir configurações', self.app)
        settings_action.triggered.connect(self.settings_window.show)
        tray_menu.addAction(settings_action)

        transforms_action = QAction('Comandos de voz e dicionário', self.app)
        transforms_action.triggered.connect(self.show_text_transforms)
        tray_menu.addAction(transforms_action)

        exit_action = QAction('Sair', self.app)
        exit_action.triggered.connect(self.exit_app)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def show_text_transforms(self):
        self.text_transforms_window.load_from_config()
        self.text_transforms_window.show()
        self.text_transforms_window.raise_()
        self.text_transforms_window.activateWindow()

    def cleanup(self):
        if self.key_listener:
            self.key_listener.stop()
        if self.input_simulator:
            self.input_simulator.cleanup()

    def exit_app(self):
        """Encerra a aplicação."""
        self.cleanup()
        QApplication.quit()

    def restart_app(self):
        """Reinicia a aplicação para aplicar as novas configurações."""
        self.cleanup()
        executable = sys.executable
        args = sys.argv if not getattr(sys, 'frozen', False) else []
        QProcess.startDetached(executable, args)
        QApplication.quit()

    def on_settings_closed(self):
        """Se as configurações forem fechadas sem salvar na primeira execução, usa os valores padrão."""
        if not os.path.exists(os.path.join(SRC_DIR, 'config.yaml')):
            QMessageBox.information(
                self.settings_window,
                'Usando valores padrão',
                'Configurações fechadas sem salvar. Valores padrão estão sendo usados.'
            )
            self.initialize_components()

    def on_activation(self):
        """Chamado quando a combinação de teclas de ativação é pressionada."""
        ConfigManager.console_print('Atalho detectado — iniciando gravação...')
        if self.result_thread and self.result_thread.isRunning():
            recording_mode = ConfigManager.get_config_value('recording_options', 'recording_mode')
            if recording_mode == 'press_to_toggle':
                self.result_thread.stop_recording()
            elif recording_mode == 'continuous':
                self.stop_result_thread()
            return

        self.start_result_thread()

    def on_deactivation(self):
        """Chamado quando a combinação de teclas de ativação é solta."""
        if ConfigManager.get_config_value('recording_options', 'recording_mode') == 'hold_to_record':
            if self.result_thread and self.result_thread.isRunning():
                self.result_thread.stop_recording()

    def start_result_thread(self):
        """Inicia a thread de resultado para gravar áudio e transcrevê-lo."""
        if self.result_thread and self.result_thread.isRunning():
            return

        self.result_thread = ResultThread(self.local_model)
        if not ConfigManager.get_config_value('misc', 'hide_status_window'):
            self.result_thread.statusSignal.connect(self.status_window.updateStatus)
            self.result_thread.audioLevelSignal.connect(self.status_window.updateLevels)
            self.status_window.closeSignal.connect(self.stop_result_thread)
        self.result_thread.resultSignal.connect(self.on_transcription_complete)
        self.result_thread.start()

    def stop_result_thread(self):
        """Para a thread de resultado."""
        if self.result_thread and self.result_thread.isRunning():
            self.result_thread.stop()

    def on_transcription_complete(self, result):
        """Quando a transcrição termina, insere o resultado e retoma a escuta do atalho."""
        if isinstance(result, ProcessedTranscription):
            if result.kind == 'keys':
                self.input_simulator.press_keys(result.keys)
            elif result.kind == 'text':
                self.input_simulator.typewrite(result.text)
        elif result:
            self.input_simulator.typewrite(result)

        if ConfigManager.get_config_value('misc', 'noise_on_completion'):
            play_sound(os.path.join(ASSETS_DIR, 'beep.wav'))

        if ConfigManager.get_config_value('recording_options', 'recording_mode') == 'continuous':
            self.start_result_thread()
        else:
            self.key_listener.start()

    def run(self):
        """Inicia a aplicação."""
        sys.exit(self.app.exec_())


if __name__ == '__main__':
    os.environ.setdefault('VOICENOTE_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    app = VoiceNoteApp()
    app.run()