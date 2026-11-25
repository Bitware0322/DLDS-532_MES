"""生成界面用的小图标资源（箭头、程序图标）。

运行： python tools/make_assets.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, \
    QPen, QLinearGradient  # noqa: E402

APP = QGuiApplication(sys.argv)

ARROW = QColor("#64748b")


def draw_chevron(name: str, up: bool, size: int = 10, scale: int = 3) -> None:
    img = QImage(size * scale, size * scale, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(ARROW, 1.6 * scale)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    w = size * scale
    path = QPainterPath()
    if up:
        path.moveTo(w * 0.22, w * 0.66)
        path.lineTo(w * 0.5, w * 0.38)
        path.lineTo(w * 0.78, w * 0.66)
    else:
        path.moveTo(w * 0.22, w * 0.38)
        path.lineTo(w * 0.5, w * 0.66)
        path.lineTo(w * 0.78, w * 0.38)
    p.drawPath(path)
    p.end()
    img.setDevicePixelRatio(scale)
    img.save(str(ASSETS / name))
    print("saved", name)


def draw_icon() -> None:
    size = 256
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor("#3b82f6"))
    grad.setColorAt(1, QColor("#1d4ed8"))
    p.setBrush(grad)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(4, 4, size - 8, size - 8), 52, 52)

    # 箱子
    p.setBrush(QColor(255, 255, 255, 235))
    p.drawRoundedRect(QRectF(52, 96, 96, 96), 10, 10)
    # 箱子上的“钢珠”
    p.setBrush(QColor("#1d4ed8"))
    p.drawEllipse(QPointF(78, 122), 10, 10)
    p.drawEllipse(QPointF(112, 122), 10, 10)
    p.drawEllipse(QPointF(78, 156), 10, 10)
    p.drawEllipse(QPointF(112, 156), 10, 10)
    # 向右箭头（下单）
    p.setBrush(QColor("#ffffff"))
    path = QPainterPath()
    path.moveTo(QPointF(166, 112))
    path.lineTo(QPointF(206, 144))
    path.lineTo(QPointF(166, 176))
    path.closeSubpath()
    p.drawPath(path)
    p.setBrush(QColor("#ffffff"))
    p.drawRect(QRectF(150, 134, 18, 20))
    p.end()

    png = ASSETS / "app_256.png"
    img.save(str(png))
    try:
        from PIL import Image
        ico = ASSETS / "app.ico"
        Image.open(png).save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                         (128, 128), (256, 256)])
        print("saved", ico.name)
    except ImportError:
        print("未安装 Pillow，跳过 .ico 生成（可用 PNG 代替）")


if __name__ == "__main__":
    draw_chevron("chevron_down.png", up=False)
    draw_chevron("chevron_up.png", up=True)
    draw_icon()
    print("资源目录：", ASSETS)
