import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "assets/themes"
REGISTRY = json.loads((DATA / "themes.json").read_text())
THEMES = {item["id"]: item for item in REGISTRY["themes"]}
DEFAULT_THEME = REGISTRY["default"]


def theme_data(name=None):
    return dict(THEMES.get(name, THEMES[DEFAULT_THEME]))


def apply_palette(app, name):
    from PySide6.QtGui import QColor, QPalette
    t = theme_data(name)
    palette = QPalette()
    for role, field in (("Window", "background"), ("WindowText", "text"), ("Base", "panel"), ("AlternateBase", "card"), ("Text", "text"), ("Button", "panel"), ("ButtonText", "text"), ("Highlight", "accent"), ("HighlightedText", "ink"), ("ToolTipBase", "card"), ("ToolTipText", "text"), ("Link", "accent")):
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(t[field]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["muted"]))
    app.setPalette(palette)
    app.setProperty("nothingx_theme", name)
    app.setStyleSheet(stylesheet(name))


def stylesheet(name=None):
    t = theme_data(name)
    return f"""
QWidget {{ color: {t['text']}; font-family: 'Inter', 'Noto Sans', sans-serif; font-size: 14px; }}
QMainWindow, QDialog, QWidget#pageBody {{ background: {t['background']}; }}
QFrame#sidebar {{ background: {t['panel']}; border-right: 1px solid {t['border']}; }}
QFrame#card {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 24px; }}
QFrame#compact {{ background: {t['panel']}; border-radius: 16px; }}
QWidget#transparent, QLabel, QCheckBox, QSlider {{ background: transparent; }}
QLabel#muted {{ color: {t['muted']}; font-size: 12px; }}
QLabel#eyebrow {{ color: {t['muted']}; font-family: monospace; font-size: 10px; letter-spacing: 1px; }}
QLabel#title {{ font-size: 28px; font-weight: 500; }}
QLabel#product {{ font-family: 'Noto Serif', 'Liberation Serif', serif; font-size: 32px; font-weight: 400; }}
QLabel#section {{ font-size: 17px; font-weight: 500; }}
QLabel#value {{ font-size: 22px; font-weight: 600; }}
QLabel#status {{ color: {t['muted']}; background: {t['panel']}; padding: 6px 12px; border-radius: 12px; font-size: 12px; }}
QLabel#banner {{ padding: 10px 14px; background: {t['panel']}; border: 1px solid {t['border']}; border-radius: 12px; }}
QPushButton {{ background: {t['panel']}; border: 1px solid {t['border']}; padding: 9px 15px; border-radius: 17px; min-height: 20px; }}
QPushButton:hover {{ border-color: {t['muted']}; background: {t['card']}; }}
QPushButton:pressed {{ background: {t['border']}; }}
QPushButton:checked, QPushButton#primary {{ background: {t['accent']}; border-color: {t['accent']}; color: {t['ink']}; }}
QPushButton:disabled {{ color: {t['muted']}; border-color: {t['border']}; }}
QPushButton#nav {{ text-align: left; padding: 13px; border: 0; background: transparent; color: {t['muted']}; }}
QPushButton#nav:checked {{ background: {t['card']}; color: {t['text']}; }}
QPushButton#subtle {{ border: 0; background: transparent; color: {t['muted']}; padding: 5px 8px; }}
QPushButton#danger {{ color: #ed5353; }}
QPushButton:focus-visible, QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{ border: 1px solid {t['accent']}; }}
QComboBox, QLineEdit, QSpinBox {{ background: {t['panel']}; border: 1px solid {t['border']}; border-radius: 12px; padding: 8px 12px; min-height: 24px; selection-background-color: {t['accent']}; selection-color: {t['ink']}; }}
QComboBox::drop-down {{ border: 0; width: 24px; }}
QComboBox QAbstractItemView, QListWidget {{ background: {t['panel']}; color: {t['text']}; selection-background-color: {t['accent']}; selection-color: {t['ink']}; border: 1px solid {t['border']}; border-radius: 12px; padding: 6px; outline: 0; }}
QListWidget::item {{ padding: 12px; border-radius: 8px; }}
QSlider::groove:horizontal {{ background: {t['border']}; height: 6px; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {t['text']}; border: 2px solid {t['card']}; width: 20px; height: 20px; margin: -8px 0; border-radius: 11px; }}
QSlider:disabled::sub-page:horizontal {{ background: {t['muted']}; }}
QProgressBar {{ background: {t['border']}; border: 0; border-radius: 2px; max-height: 4px; }}
QProgressBar::chunk {{ background: {t['text']}; border-radius: 2px; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 5px; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 2px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QTabWidget::pane {{ border: 0; background: transparent; padding-top: 15px; }}
QTabBar::tab {{ background: {t['panel']}; color: {t['muted']}; padding: 10px 20px; margin-right: 6px; border-radius: 16px; }}
QTabBar::tab:selected {{ background: {t['card']}; color: {t['text']}; }}
QMenu {{ background: {t['card']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 12px; padding: 8px; }}
QMenu::item {{ padding: 8px 24px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t['accent']}; color: {t['ink']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 6px 10px; }}
QToolTip {{ background: {t['card']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 7px; }}
"""
