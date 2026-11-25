"""界面主题（浅色，蓝色主色调，与产线 MES 视觉风格保持一致）。"""
from __future__ import annotations

import sys
from pathlib import Path

BG = "#f4f7fb"
CARD = "#ffffff"
BORDER = "#e2e8f0"
TEXT = "#0f172a"
MUTED = "#64748b"
PRIMARY = "#2563eb"
PRIMARY_DARK = "#1d4ed8"
GREEN = "#15803d"
RED = "#dc2626"
AMBER = "#d97706"


def asset_url(name: str) -> str:
    """打包前后都能定位到 assets 目录的小图标。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return (base / "assets" / name).as_posix()


_ARROW_UP = asset_url("chevron_up.png")
_ARROW_DOWN = asset_url("chevron_down.png")

QSS = f"""
* {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QWidget#Root {{ background: {BG}; }}

QFrame#Header {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#AppTitle {{ font-size: 18px; font-weight: 700; }}
QLabel#AppSub {{ color: {MUTED}; font-size: 12px; }}
QLabel#ConnText {{ font-size: 12px; color: {MUTED}; }}

QFrame#Card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#CardCaption {{ color: {MUTED}; font-size: 12px; }}
QLabel#CardValue {{ font-size: 16px; font-weight: 700; }}

QFrame#Panel {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#PanelTitle {{ font-weight: 700; font-size: 14px; }}
QLabel#Hint {{ color: {MUTED}; font-size: 12px; }}

QPushButton {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 7px 16px;
    min-height: 20px;
}}
QPushButton:hover {{ background: #eef4ff; border-color: #bfd4fb; }}
QPushButton:pressed {{ background: #e0eaff; }}
QPushButton:disabled {{ color: #94a3b8; background: #f1f5f9; border-color: {BORDER}; }}

QPushButton#Primary {{
    background: {PRIMARY}; border: 1px solid {PRIMARY}; color: #ffffff; font-weight: 600;
}}
QPushButton#Primary:hover {{ background: {PRIMARY_DARK}; border-color: {PRIMARY_DARK}; }}
QPushButton#Primary:disabled {{ background: #b9cdf5; border-color: #b9cdf5; color: #f8fafc; }}

QPushButton#Success {{
    background: #16a34a; border: 1px solid #16a34a; color: #ffffff; font-weight: 600;
}}
QPushButton#Success:hover {{ background: #15803d; border-color: #15803d; }}
QPushButton#Success:disabled {{ background: #bfe3c9; border-color: #bfe3c9; color: #f8fafc; }}

QPushButton#Danger {{ color: {RED}; border-color: #f3c9c9; }}
QPushButton#Danger:hover {{ background: #fef2f2; }}

QPushButton#Link {{
    background: transparent; border: none; color: {PRIMARY}; padding: 4px 6px;
}}
QPushButton#Link:hover {{ color: {PRIMARY_DARK}; text-decoration: underline; }}

QTableWidget {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: #eef2f7;
    selection-background-color: #e6efff;
    selection-color: {TEXT};
    alternate-background-color: #fafcff;
}}
QTableWidget::item {{ padding: 4px 8px; }}
QTableWidget::item:selected, QTableView::item:selected {{
    background: #e6efff;
    color: {TEXT};
}}
QHeaderView::section {{
    background: #f7f9fc;
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 9px 8px;
    font-weight: 600;
}}
QTableCornerButton::section {{ background: #f7f9fc; border: none; }}

QPlainTextEdit {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px;
    font-family: "Consolas", "Microsoft YaHei UI", monospace;
    font-size: 12px;
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {CARD};
    border: 1px solid #cfd8e4;
    border-radius: 6px;
    padding: 6px 8px;
    min-height: 18px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {PRIMARY}; }}
QComboBox::drop-down {{ border: none; width: 22px; background: transparent; }}
QComboBox::down-arrow {{ image: url({_ARROW_DOWN}); width: 10px; height: 10px; margin-right: 6px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 20px; border: none; border-left: 1px solid #e6ecf4;
    border-top-right-radius: 6px; background: #f7f9fc;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 20px; border: none; border-left: 1px solid #e6ecf4;
    border-bottom-right-radius: 6px; background: #f7f9fc;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: #eaf1ff; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({_ARROW_UP}); width: 9px; height: 9px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({_ARROW_DOWN}); width: 9px; height: 9px;
}}

QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}

QCheckBox {{ spacing: 6px; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; background: {CARD}; }}
QTabBar::tab {{
    background: transparent; padding: 7px 16px; border-bottom: 2px solid transparent;
    color: {MUTED};
}}
QTabBar::tab:selected {{ color: {PRIMARY}; border-bottom: 2px solid {PRIMARY}; font-weight: 600; }}

QStatusBar {{ background: {CARD}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #cbd5e1; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #cbd5e1; border-radius: 5px; min-width: 24px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QMenu {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 5px; }}
QMenu::item:selected {{ background: #eef4ff; }}
QToolTip {{
    background: #1e293b; color: #ffffff; border: none; padding: 6px 8px; border-radius: 5px;
}}
"""
