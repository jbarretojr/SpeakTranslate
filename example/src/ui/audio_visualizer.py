from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QWidget


class AudioVisualizerWidget(QWidget):
    """Barras verticais que pulsam conforme o nível de áudio por banda de frequência."""

    def __init__(self, num_bars=8, parent=None):
        super().__init__(parent)
        self.num_bars = num_bars
        self.levels = [0.0] * num_bars
        self.decay = 0.82
        self.bar_color = QColor('#4a90d9')
        self.setFixedSize(120, 48)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._decay_levels)
        self._timer.start(40)

    def set_levels(self, levels):
        if not levels:
            return
        count = min(len(levels), self.num_bars)
        for index in range(count):
            value = max(0.0, min(1.0, float(levels[index])))
            self.levels[index] = max(value, self.levels[index] * self.decay)
        self.update()

    def reset(self):
        self.levels = [0.0] * self.num_bars
        self.update()

    def _decay_levels(self):
        changed = False
        for index, level in enumerate(self.levels):
            if level > 0.01:
                self.levels[index] = level * self.decay
                changed = True
            elif level > 0:
                self.levels[index] = 0.0
                changed = True
        if changed:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        gap = 3
        bar_width = max(4, (width - gap * (self.num_bars + 1)) // self.num_bars)

        for index, level in enumerate(self.levels):
            bar_height = max(4, int(height * level))
            x = gap + index * (bar_width + gap)
            y = height - bar_height
            painter.setBrush(self.bar_color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(x, y, bar_width, bar_height, 2, 2)
