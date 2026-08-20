import sys
import os
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel, QHBoxLayout, QVBoxLayout, QWidget

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui.base_window import BaseWindow
from ui.audio_visualizer import AudioVisualizerWidget
from utils import ASSETS_DIR, ConfigManager

class StatusWindow(BaseWindow):
    statusSignal = pyqtSignal(str)
    closeSignal = pyqtSignal()

    def __init__(self):
        """Inicializa a janela de status."""
        super().__init__('Status do VoiceNote', 360, 140)
        self.initStatusUI()
        self.statusSignal.connect(self.updateStatus)

    def initStatusUI(self):
        """Inicializa a interface de status."""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        left_column = QVBoxLayout()
        left_column.setSpacing(4)

        self.visualizer = AudioVisualizerWidget()
        self.visualizer.setVisible(ConfigManager.get_config_value('misc', 'show_audio_visualizer'))
        left_column.addWidget(self.visualizer, alignment=Qt.AlignCenter)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(32, 32)
        microphone_path = os.path.join(ASSETS_DIR, 'microphone.png')
        pencil_path = os.path.join(ASSETS_DIR, 'pencil.png')
        self.microphone_pixmap = QPixmap(microphone_path).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.pencil_pixmap = QPixmap(pencil_path).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.icon_label.setPixmap(self.microphone_pixmap)
        self.icon_label.setAlignment(Qt.AlignCenter)
        left_column.addWidget(self.icon_label, alignment=Qt.AlignCenter)

        content_layout.addLayout(left_column)

        self.status_label = QLabel('Gravando...')
        self.status_label.setFont(QFont('Segoe UI', 12))
        self.status_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        content_layout.addWidget(self.status_label, 1)

        wrapper = QWidget()
        wrapper.setLayout(content_layout)
        self.main_layout.addWidget(wrapper)
        
    def show(self):
        """Posiciona a janela no centro inferior da tela e a exibe."""
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        window_width = self.width()
        window_height = self.height()

        x = (screen_width - window_width) // 2
        y = screen_height - window_height - 120

        self.move(x, y)
        super().show()
        
    def closeEvent(self, event):
        """Emite o sinal de fechamento quando a janela é fechada."""
        self.closeSignal.emit()
        super().closeEvent(event)

    @pyqtSlot(list)
    def updateLevels(self, levels):
        if self.visualizer.isVisible():
            self.visualizer.set_levels(levels)

    @pyqtSlot(str)
    def updateStatus(self, status):
        """Atualiza a janela de status com base no status informado."""
        if status == 'recording':
            self.icon_label.setPixmap(self.microphone_pixmap)
            self.status_label.setText('Gravando...')
            self.visualizer.reset()
            self.visualizer.setVisible(ConfigManager.get_config_value('misc', 'show_audio_visualizer'))
            self.show()
        elif status == 'transcribing':
            self.icon_label.setPixmap(self.pencil_pixmap)
            self.status_label.setText('Transcrevendo...')
            self.visualizer.reset()

        if status in ('idle', 'error', 'cancel'):
            self.visualizer.reset()
            self.close()


if __name__ == '__main__':
    ConfigManager.initialize()
    app = QApplication(sys.argv)
    
    status_window = StatusWindow()
    status_window.show()

    QTimer.singleShot(3000, lambda: status_window.statusSignal.emit('transcribing'))
    QTimer.singleShot(6000, lambda: status_window.statusSignal.emit('idle'))
    
    sys.exit(app.exec_())
