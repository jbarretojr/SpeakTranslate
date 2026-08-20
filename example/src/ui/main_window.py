import os
import sys
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QPushButton, QHBoxLayout, QVBoxLayout
from PyQt5.QtCore import pyqtSignal

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui.base_window import BaseWindow

class MainWindow(BaseWindow):
    openSettings = pyqtSignal()
    openTextTransforms = pyqtSignal()
    startListening = pyqtSignal()
    closeApp = pyqtSignal()

    def __init__(self):
        """Inicializa a janela principal."""
        super().__init__('VoiceNote', 360, 240)
        self.initMainUI()

    def initMainUI(self):
        """Inicializa a interface principal."""
        start_btn = QPushButton('Iniciar')
        start_btn.setFont(QFont('Segoe UI', 10))
        start_btn.setFixedSize(140, 50)
        start_btn.clicked.connect(self.startPressed)

        settings_btn = QPushButton('Configurações')
        settings_btn.setFont(QFont('Segoe UI', 10))
        settings_btn.setFixedSize(140, 50)
        settings_btn.clicked.connect(self.openSettings.emit)

        transforms_btn = QPushButton('Comandos e dicionário')
        transforms_btn.setFont(QFont('Segoe UI', 10))
        transforms_btn.setFixedSize(140, 50)
        transforms_btn.clicked.connect(self.openTextTransforms.emit)

        top_row = QHBoxLayout()
        top_row.addStretch(1)
        top_row.addWidget(start_btn)
        top_row.addStretch(1)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        bottom_row.addWidget(settings_btn)
        bottom_row.addWidget(transforms_btn)
        bottom_row.addStretch(1)

        layout = QVBoxLayout()
        layout.addStretch(1)
        layout.addLayout(top_row)
        layout.addSpacing(12)
        layout.addLayout(bottom_row)
        layout.addStretch(1)

        self.main_layout.addLayout(layout)

    def closeEvent(self, event):
        """Encerra a aplicação quando a janela principal é fechada."""
        self.closeApp.emit()

    def startPressed(self):
        """Emite o sinal startListening quando o botão Iniciar é pressionado."""
        self.startListening.emit()
        self.hide()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
