"""界面小型复用控件。"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QTableWidget, QVBoxLayout, QWidget

from . import theme


class StatusDot(QWidget):
    """连接状态指示点。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._color = QColor(theme.RED)
        self.setFixedSize(QSize(12, 12))

    def set_state(self, state: str) -> None:
        self._color = QColor({"ok": theme.GREEN, "warn": theme.AMBER,
                              "error": theme.RED}.get(state, theme.RED))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        glow = QColor(self._color)
        glow.setAlpha(60)
        painter.setBrush(glow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 12, 12)
        painter.setBrush(self._color)
        painter.drawEllipse(2, 2, 8, 8)
        painter.end()


class InfoCard(QFrame):
    """一个“标题 + 数值”的信息卡。"""

    def __init__(self, caption: str, value: str = "-", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(2)
        self.caption = QLabel(caption)
        self.caption.setObjectName("CardCaption")
        self.value = QLabel(value)
        self.value.setObjectName("CardValue")
        layout.addWidget(self.caption)
        layout.addWidget(self.value)

    def set_value(self, text: str, color: str | None = None) -> None:
        self.value.setText(text)
        self.value.setStyleSheet(f"color: {color};" if color else "")


class CardRow(QWidget):
    """一行信息卡，等宽排列。"""

    def __init__(self, specs: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.cards: dict[str, InfoCard] = {}
        for key, caption in specs:
            card = InfoCard(caption)
            self.cards[key] = card
            layout.addWidget(card, 1)


class OrderTable(QTableWidget):
    """订单列表，空表时显示引导文字。"""

    EMPTY_TEXT = "暂无订单，点击「新建订单」创建"

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self.rowCount() > 0:
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor(theme.MUTED))
        font = self.font()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(self.viewport().rect(), Qt.AlignCenter, self.EMPTY_TEXT)
        painter.end()
