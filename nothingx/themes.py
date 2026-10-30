import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "assets/themes"
REGISTRY = json.loads((DATA / "themes.json").read_text())
THEMES = {item["id"]: item for item in REGISTRY["themes"]}
DEFAULT_THEME = REGISTRY["default"]


def theme_data(name=None):
    return dict(THEMES.get(name, THEMES[DEFAULT_THEME]))


def stylesheet(name=None):
    t = theme_data(name)
    return f"""
QWidget {{ background: {t['background']}; color: {t['text']}; font-family: 'Inter', 'Helvetica Neue', 'Noto Sans', sans-serif; font-size: 14px; }}
QMainWindow {{ background: {t['background']}; }}
QFrame#sidebar {{ background: {t['panel']}; border-right: 1px solid {t['border']}; }}
QFrame#card {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 24px; }}
QLabel, QCheckBox, QSlider {{ background: transparent; }}
QLabel#muted {{ color: {t['muted']}; }}
QLabel#eyebrow {{ color: {t['accent']}; font-family: monospace; font-size: 11px; font-weight: 600; }}
QLabel#title {{ font-size: 32px; font-weight: 600; letter-spacing: -1px; }}
QLabel#section {{ font-size: 18px; font-weight: 600; }}
QLabel#banner {{ padding: 12px 15px; background: {t['panel']}; border: 1px solid {t['border']}; border-radius: 16px; }}
QPushButton {{ background: {t['panel']}; border: 1px solid {t['border']}; padding: 10px 17px; border-radius: 18px; font-weight: 500; min-height: 18px; }}
QPushButton:hover {{ border-color: {t['accent']}; }}
QPushButton:pressed, QPushButton:checked, QPushButton#primary {{ background: {t['accent']}; border-color: {t['accent']}; color: {t['ink']}; }}
QPushButton:disabled {{ color: {t['muted']}; border-color: {t['border']}; }}
QPushButton#nav {{ text-align: left; padding: 13px; border: 0; background: transparent; color: {t['muted']}; }}
QPushButton#nav:checked {{ background: {t['card']}; color: {t['accent']}; }}
QPushButton#nav:hover {{ background: {t['card']}; }}
QComboBox, QLineEdit, QSpinBox {{ background: {t['panel']}; border: 1px solid {t['border']}; border-radius: 12px; padding: 9px; min-height: 22px; selection-background-color: {t['accent']}; }}
QComboBox:disabled {{ color: {t['muted']}; }}
QComboBox QAbstractItemView {{ background: {t['card']}; color: {t['text']}; selection-background-color: {t['accent']}; selection-color: {t['ink']}; padding: 6px; }}
QSlider::groove:horizontal {{ background: {t['border']}; height: 5px; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {t['text']}; border: 3px solid {t['accent']}; width: 15px; height: 15px; margin: -8px 0; border-radius: 10px; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 6px; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 3px; min-height: 25px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolTip {{ background: {t['card']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 7px; }}
"""
