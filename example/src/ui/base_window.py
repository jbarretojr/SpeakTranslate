from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QBrush, QColor, QFont, QPainterPath, QGuiApplication
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QMainWindow


class BaseWindow(QMainWindow):
    def __init__(self, title, width, height):
        """Inicializa a janela base."""
        super().__init__()
        self.initUI(title, width, height)
        self.setWindowPosition()
        self.is_dragging = False

    def initUI(self, title, width, height):
        """Inicializa a interface do usuário."""
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(width, height)

        self.main_widget = QWidget(self)
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # Barra de título
        title_bar = QWidget()
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel('VoiceNote')
        title_label.setFont(QFont('Segoe UI', 12, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #404040;")

        close_button_widget = QWidget()
        close_button_layout = QHBoxLayout(close_button_widget)
        close_button_layout.setContentsMargins(0, 0, 0, 0)

        close_button = QPushButton('×')
        close_button.setFixedSize(25, 25)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #404040;
            }
            QPushButton:hover {
                color: #000000;
            }
        """)
        close_button.clicked.connect(self.handleCloseButton)

        close_button_layout.addWidget(close_button, alignment=Qt.AlignRight)

        title_bar_layout.addWidget(QWidget(), 1)  # espaçador esquerdo
        title_bar_layout.addWidget(title_label, 3)  # título
        title_bar_layout.addWidget(close_button_widget, 1)  # botão fechar

        self.main_layout.addWidget(title_bar)
        self.setCentralWidget(self.main_widget)

    def setWindowPosition(self):
        """Centraliza a janela na tela."""
        center_point = QGuiApplication.primaryScreen().availableGeometry().center()
        frame_geometry = self.frameGeometry()
        frame_geometry.moveCenter(center_point)
        self.move(frame_geometry.topLeft())

    def handleCloseButton(self):
        """Fecha a janela."""
        self.close()

    def mousePressEvent(self, event):
        """Permite mover a janela ao clicar e arrastar em qualquer lugar."""
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.start_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """Move a janela durante o arraste."""
        if Qt.LeftButton and self.is_dragging:
            self.move(event.globalPos() - self.start_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Interrompe o arraste da janela."""
        self.is_dragging = False

    def paintEvent(self, event):
        """Desenha um retângulo arredondado com fundo branco semitransparente."""
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 20, 20)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)
