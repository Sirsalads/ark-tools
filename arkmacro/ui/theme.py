"""Design tokens and the application stylesheet.

Same visual language as A.N.S Watcher: a petrol-to-black canvas, soft cyan
glows, translucent glass cards. Amber stays reserved for anything that can
cost you items.
"""

# canvas
INK = "#070F14"
INK_TOP = "#10242E"
BG = "#0A1A22"

# opaque equivalents, for popups and painted widgets
SURFACE = "#152831"
SURFACE_2 = "#1B333E"
SURFACE_3 = "#234451"
BORDER = "#1E3A46"
BORDER_SOFT = "#14262F"

TEXT = "#E9F4F8"
TEXT_DIM = "#A9C3CC"
MUTED = "#6E8A95"
ACCENT = "#40DCF0"
ACCENT_HOVER = "#7DEBFA"
ACCENT_DEEP = "#1882A0"
OK = "#3ED598"
WARN = "#F7B32B"
ERR = "#F0555F"

# glass fills used through the stylesheet — dark enough that the brand
# backdrop reads as texture behind the panels, never through the text
GLASS = "rgba(13, 30, 39, 0.72)"
GLASS_STRONG = "rgba(30, 58, 70, 0.85)"
GLASS_LINE = "rgba(64, 220, 240, 0.16)"
GLASS_LINE_SOFT = "rgba(64, 220, 240, 0.09)"
FIELD = "rgba(5, 12, 16, 0.68)"

DISPLAY_FONT = '"Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI"'
TEXT_FONT = '"Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif'

QSS = f"""
* {{
    font-family: {TEXT_FONT};
    font-size: 13px;
    color: {TEXT};
}}

/* the Backdrop paints the canvas; the sheet only draws the frame */
#root {{
    background: transparent;
    border: 1px solid {GLASS_LINE};
    border-radius: 14px;
}}
QDialog {{ background: {INK}; }}

/* ------------------------------------------------------------- title bar */
#titlebar {{ background: transparent; }}
#logoMark {{
    font-family: {DISPLAY_FONT};
    font-size: 15px; font-weight: 800; letter-spacing: 1px; color: {ACCENT};
}}
#logoText {{
    font-family: {DISPLAY_FONT};
    font-size: 15px; font-weight: 600; letter-spacing: 3px; color: {TEXT};
}}
#logoSub {{ font-size: 11px; color: {MUTED}; letter-spacing: 0.4px; }}
#updatePill {{
    background: rgba(64, 220, 240, 0.14);
    border: 1px solid {GLASS_LINE};
    border-radius: 13px;
    color: {ACCENT};
    font-size: 11px; font-weight: 600;
    padding: 4px 13px;
}}
#updatePill:hover {{ background: rgba(64, 220, 240, 0.26); }}
#winbtn {{ background: transparent; border: none; border-radius: 7px; }}
#winbtn:hover {{ background: {GLASS_STRONG}; }}
#closebtn:hover {{ background: {ERR}; }}

/* --------------------------------------------------------------- sidebar */
#sidebar {{
    background: rgba(8, 19, 25, 0.80);
    border-right: 1px solid {GLASS_LINE_SOFT};
    border-bottom-left-radius: 14px;
}}
#navSection {{
    color: {MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 1.5px;
    padding: 0px 14px;
}}
#navbtn {{
    background: transparent; border: none; border-radius: 9px;
    padding: 9px 12px; text-align: left; color: {TEXT_DIM}; font-size: 13px;
}}
#navbtn:hover {{ background: {GLASS}; color: {TEXT}; }}
#navbtn:checked {{
    background: rgba(64, 220, 240, 0.14);
    color: {ACCENT};
    font-weight: 600;
}}
#footNote {{ color: {MUTED}; font-size: 11px; padding: 0px 14px; }}

/* ----------------------------------------------------------------- cards */
#card {{
    background: {GLASS};
    border: 1px solid {GLASS_LINE_SOFT};
    border-radius: 12px;
}}
#cardAccent {{
    background: {GLASS};
    border: 1px solid {GLASS_LINE};
    border-radius: 12px;
}}
#cardTitle {{
    font-family: {DISPLAY_FONT};
    font-size: 13px; font-weight: 600; letter-spacing: 0.2px;
}}
#cardSub, #hint {{ font-size: 11px; color: {MUTED}; }}
#warnHint {{ font-size: 11px; color: {WARN}; }}
#pageTitle {{
    font-family: {DISPLAY_FONT};
    font-size: 22px; font-weight: 600; letter-spacing: -0.2px;
}}
#pageSub {{ font-size: 12px; color: {MUTED}; }}
#fieldLabel {{ color: {TEXT_DIM}; font-size: 12px; }}
#divider {{ background: {GLASS_LINE_SOFT}; }}
#stepNum {{
    color: {ACCENT}; font-size: 11px; font-weight: 700;
    background: rgba(64, 220, 240, 0.12); border-radius: 9px;
}}

/* ---------------------------------------------------------------- inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    background: {FIELD};
    border: 1px solid {GLASS_LINE};
    border-radius: 8px;
    padding: 6px 9px;
    selection-background-color: {ACCENT_DEEP};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border-color: rgba(64, 220, 240, 0.30);
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {MUTED}; }}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 17px; background: rgba(255, 255, 255, 0.05); border: none;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ border-top-right-radius: 7px; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    border-bottom-right-radius: 7px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: rgba(64, 220, 240, 0.20);
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: none; width: 0; height: 0;
    border-left: 3px solid transparent; border-right: 3px solid transparent;
    border-bottom: 4px solid {TEXT_DIM};
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: none; width: 0; height: 0;
    border-left: 3px solid transparent; border-right: 3px solid transparent;
    border-top: 4px solid {TEXT_DIM};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{
    image: none; width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_DIM}; margin-right: 7px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE}; border: 1px solid {GLASS_LINE}; border-radius: 8px;
    selection-background-color: {ACCENT_DEEP}; outline: none; padding: 4px;
}}

/* --------------------------------------------------------------- buttons */
QPushButton {{
    background: {GLASS};
    border: 1px solid {GLASS_LINE};
    border-radius: 8px;
    padding: 7px 14px;
}}
QPushButton:hover {{
    background: {GLASS_STRONG}; border-color: rgba(64, 220, 240, 0.35);
}}
QPushButton:pressed {{ background: rgba(7, 15, 20, 0.60); }}
QPushButton:disabled {{ color: {MUTED}; border-color: {GLASS_LINE_SOFT}; }}
#primary {{
    background: {ACCENT}; border: none; color: #04222B;
    font-weight: 700; padding: 11px 20px; border-radius: 9px;
}}
#primary:hover {{ background: {ACCENT_HOVER}; color: #04222B; }}
#danger {{
    background: {ERR}; border: none; color: #ffffff;
    font-weight: 700; padding: 11px 20px; border-radius: 9px;
}}
#danger:hover {{ background: #FF6C75; color: #ffffff; }}
#tiny {{ padding: 5px 10px; font-size: 12px; }}

/* ----------------------------------------------------------------- lists */
QListWidget {{
    background: rgba(7, 15, 20, 0.45);
    border: 1px solid {GLASS_LINE};
    border-radius: 9px;
    padding: 5px; outline: none;
}}
QListWidget::item {{ padding: 5px 8px; border-radius: 6px; min-height: 20px; }}
QListWidget::item:selected {{ background: {ACCENT_DEEP}; color: #ffffff; }}
QListWidget::item:hover {{ background: {GLASS}; }}
QListWidget::indicator {{
    width: 15px; height: 15px; border: 1px solid rgba(64, 220, 240, 0.30);
    border-radius: 4px; background: rgba(7, 15, 20, 0.60);
}}
QListWidget::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

/* ------------------------------------------------------------- scrollbar */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: rgba(64, 220, 240, 0.20); border-radius: 4px; min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(64, 220, 240, 0.42); }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* ------------------------------------------------------------------ misc */
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border: 1px solid rgba(64, 220, 240, 0.30);
    border-radius: 4px; background: rgba(7, 15, 20, 0.60);
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QToolTip {{
    background: {SURFACE_2}; color: {TEXT}; border: 1px solid {GLASS_LINE};
    border-radius: 6px; padding: 6px 9px;
}}
#log {{
    background: rgba(4, 9, 12, 0.66);
    border: 1px solid {GLASS_LINE_SOFT}; border-radius: 10px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px; padding: 9px;
}}
#statValue {{ font-family: {DISPLAY_FONT}; font-size: 25px; font-weight: 700; }}
#statLabel {{
    font-size: 10px; color: {MUTED}; font-weight: 600; letter-spacing: 1.2px;
}}
#thumb {{
    background: rgba(7, 15, 20, 0.55);
    border: 1px solid {GLASS_LINE}; border-radius: 8px;
}}
"""
