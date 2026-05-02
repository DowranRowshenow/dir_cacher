from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QPushButton, QLabel, QLineEdit,
    QProgressBar, QFrame, QSizePolicy, QScrollArea
)
from PySide6.QtCore import Qt, QSize, Signal, QPropertyAnimation, QEasingCurve, QTimer, QEvent
from PySide6.QtGui import QColor, QPainter, QPixmap, QFont, QBrush
import qtawesome as qta

from ui.explorer_table import ExplorerTable
from ui.settings_panel import SettingsPanel
from ui.styles import STYLESHEET


# ──────────────────────────────────────────────────────────
# Sidebar nav button — matches PowerToys exactly:
#   small colored icon (no box) + text, active = blue bg
# ──────────────────────────────────────────────────────────
class NavButton(QWidget):
    def __init__(self, label: str, icon: str, icon_color: str,
                 on_click, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._on_click = on_click
        self._active = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)
        
        self._colored_icon = qta.icon(icon, color=icon_color).pixmap(QSize(18, 18))
        self._active_icon = qta.icon(icon, color="#ffffff").pixmap(QSize(18, 18))
        self._inactive_icon = qta.icon(icon, color="#aaaaaa").pixmap(QSize(18, 18))
        self.is_dark = False
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(8)

        self._indicator = QFrame()
        self._indicator.setFixedWidth(3)
        self._indicator.setFixedHeight(16)
        self._indicator.setStyleSheet("background-color: transparent; border-radius: 1.5px;")

        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(20, 20)
        self._icon_lbl.setStyleSheet("border: none; background: transparent;")

        self._text_lbl = QLabel(label)
        self._text_lbl.setFont(QFont("Segoe UI Variable Display", 10))
        self._text_lbl.setStyleSheet("color: #aaaaaa; background: transparent; border: none;")

        layout.addWidget(self._indicator)
        layout.addSpacing(6)
        layout.addWidget(self._icon_lbl)
        layout.addWidget(self._text_lbl)
        self._apply(False)

    # ── state ──────────────────────────────────────────────
    def set_active(self, active: bool):
        self._active = active
        self._apply(active)

    def _apply(self, active: bool):
        if active:
            bg = "#3d3d3d" if self.is_dark else "#ffffff"
            fg = "#ffffff" if self.is_dark else "#1a1a1a"
            self.setStyleSheet(f"NavButton {{ background-color: {bg}; border-radius: 4px; border: none; }}")
            self._indicator.setStyleSheet("background-color: #0078d4; border-radius: 1.5px; border: none;")
            self._icon_lbl.setPixmap(self._colored_icon)
            self._text_lbl.setStyleSheet(f"color: {fg}; font-weight: 600; background: transparent; border: none;")
        else:
            self.setStyleSheet(f"NavButton {{ background-color: transparent; border-radius: 4px; border: none; }}")
            self._indicator.setStyleSheet("background-color: transparent; border: none;")
            self._icon_lbl.setPixmap(self._inactive_icon)
            self._text_lbl.setStyleSheet("color: #aaaaaa; font-weight: 400; background: transparent; border: none;")

    def setText(self, text: str):
        self._text_lbl.setText(text)

    # ── events ─────────────────────────────────────────────
    def mousePressEvent(self, _):
        self._on_click()

    def enterEvent(self, _):
        if not self._active:
            hover_bg = "rgba(255,255,255,0.1)" if self.is_dark else "#e5e5e5"
            self.setStyleSheet(f"NavButton {{ background-color: {hover_bg}; border-radius: 4px; }}")

    def leaveEvent(self, _):
        self._apply(self._active)



def _h_sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet("background-color: #e5e5e5; border: none; margin: 0 12px;")
    return f


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setFont(QFont("Segoe UI Variable Text", 8, QFont.Bold))
    lbl.setStyleSheet("color: #888888; padding: 6px 14px 2px 14px; letter-spacing: 0.8px; background: transparent; border: none;")
    return lbl


# ──────────────────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PathLog")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.resize(1080, 720)
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(STYLESHEET)

        self.central_widget = QWidget()
        self.central_widget.setObjectName("MainWindowContent")
        self.central_widget.setStyleSheet("""
            #MainWindowContent {
                background: #ffffff;
                border: 1px solid #c8c8c8;
                border-radius: 8px;
            }
        """)
        self.setCentralWidget(self.central_widget)
        
        layout = QVBoxLayout(self.central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Win11 Custom Title Bar ──────────────────────────
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(32)
        self.title_bar.setObjectName("TitleBar")
        self.title_bar.mouseMoveEvent = self.mouseMoveEvent
        self.title_bar.mousePressEvent = self.mousePressEvent
        tb_layout = QHBoxLayout(self.title_bar)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(0)

        self.title_label = QLabel("DirCache Explorer")
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("color: #666666; font-size: 11px; font-family: 'Segoe UI Variable Display';")
        
        # Center the title by using a container with a layout
        title_container = QWidget()
        title_clayout = QHBoxLayout(title_container)
        title_clayout.setContentsMargins(140, 0, 140, 0) # Pad to keep center
        title_clayout.addWidget(self.title_label)
        
        tb_layout.addWidget(title_container, 1)

        btn_style = """
            QPushButton {
                background: transparent; border: none; width: 46px; height: 32px;
                font-size: 16px;
            }
            QPushButton:hover { background: rgba(0,0,0,0.1); }
        """
        self.min_btn = QPushButton("−")
        self.min_btn.setStyleSheet(btn_style)
        self.min_btn.clicked.connect(self.showMinimized)
        
        self.max_btn = QPushButton("▢")
        self.max_btn.setStyleSheet(btn_style)
        self.max_btn.clicked.connect(self._toggle_maximize)
        
        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("CloseBtn")
        self.close_btn.setStyleSheet(btn_style)
        self.close_btn.clicked.connect(self.close)

        tb_layout.addWidget(self.min_btn)
        tb_layout.addWidget(self.max_btn)
        tb_layout.addWidget(self.close_btn)
        
        layout.addWidget(self.title_bar)

        # ── Sidebar & Stack ───────────────────────────────
        content_row = QWidget()
        root_layout = QHBoxLayout(content_row)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        layout.addWidget(content_row, 1)

        self.sidebar_widget = QWidget()
        self.sidebar_widget.setObjectName("Sidebar")
        self.sidebar_widget.setFixedWidth(240)
        self.sidebar_widget.setStyleSheet("background: #f3f3f3; border-right: 1px solid #ebebeb; border-bottom-left-radius: 8px;")
        sb_layout = QVBoxLayout(self.sidebar_widget)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        # App name row
        app_row = QWidget()
        app_row.setFixedHeight(52)
        app_row.setStyleSheet("background: transparent; border: none;")
        ar_layout = QHBoxLayout(app_row)
        ar_layout.setContentsMargins(14, 0, 14, 0)
        ar_layout.setSpacing(10)
        app_icon_lbl = QLabel()
        app_icon_lbl.setFixedSize(20, 20)
        app_icon_lbl.setPixmap(qta.icon("fa5s.database", color="#0078d4").pixmap(QSize(18, 18)))
        app_icon_lbl.setStyleSheet("border: none;")
        self.app_logo_lbl = QLabel("DirCache")
        self.app_logo_lbl.setFont(QFont("Segoe UI Variable Display", 12, QFont.Bold))
        self.app_logo_lbl.setStyleSheet("color: #1a1a1a; background: transparent; border: none;")
        ar_layout.addWidget(app_icon_lbl)
        ar_layout.addWidget(self.app_logo_lbl)
        ar_layout.addStretch()
        sb_layout.addWidget(app_row)
        sb_layout.addWidget(_h_sep())
        sb_layout.addSpacing(6)

        # Nav items
        self._nav_btns: list[NavButton] = []
        nav_pad = QWidget()
        nav_pad.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_pad)
        nav_layout.setContentsMargins(6, 0, 6, 0)
        nav_layout.setSpacing(2)

        self.nav_explorer = self._add_nav(nav_layout, "Explorer",  "fa5s.folder-open", "#0078d4", 0)
        self.nav_scan = self._add_nav(nav_layout, "Scan Now",  "fa5s.search",      "#107c10", 1)
        nav_layout.addSpacing(6)
        nav_layout.addWidget(_h_sep())
        nav_layout.addWidget(_section_label("Configure"))
        self.nav_settings = self._add_nav(nav_layout, "Settings",  "fa5s.cog",         "#6b69d6", 2)
        nav_layout.addStretch()

        sb_layout.addWidget(nav_pad, 1)
        sb_layout.addWidget(_h_sep())

        # Bottom static items
        bottom_pad = QWidget()
        bottom_pad.setStyleSheet("background: transparent;")
        bot_layout = QVBoxLayout(bottom_pad)
        bot_layout.setContentsMargins(6, 6, 6, 8)
        bot_layout.setSpacing(2)

        version_lbl = QLabel("DirCache v1.1.0")
        version_lbl.setStyleSheet("color: #aaaaaa; font-size: 11px; padding-left: 14px; background: transparent; border: none;")
        bot_layout.addWidget(version_lbl)

        sb_layout.addWidget(bottom_pad)

        # ── Content Stack ─────────────────────────────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: #ffffff;")

        self.stack.addWidget(self._build_explorer_page())
        self.stack.addWidget(self._build_scan_page())

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidget(SettingsPanel())
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QFrame.NoFrame)
        self.settings_scroll.setStyleSheet("background: #ffffff; border: none;")
        self.settings_panel = self.settings_scroll.widget()
        self.stack.addWidget(self.settings_scroll)

        root_layout.addWidget(self.sidebar_widget)
        root_layout.addWidget(self.stack, 1)

        # Activate first
        self._nav_btns[0].set_active(True)

    # ── Nav helper ────────────────────────────────────────
    def _add_nav(self, layout, label, icon, color, index):
        btn = NavButton(label, icon, color, lambda idx=index: self._navigate(idx))
        self._nav_btns.append(btn)
        layout.addWidget(btn)
        return btn

    def _navigate(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_btns):
            btn.set_active(i == index)

    # ── Page: Explorer ────────────────────────────────────
    def _build_explorer_page(self) -> QWidget:
        self.explorer_page = QWidget()
        self.explorer_page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self.explorer_page)
        layout.setContentsMargins(40, 32, 40, 16)
        layout.setSpacing(0)

        # Title
        self.explorer_title = QLabel("Explorer")
        self.explorer_title.setFont(QFont("Segoe UI Variable Display", 22, QFont.Bold))
        self.explorer_title.setStyleSheet("font-size: 24px; font-weight: 700; background: transparent; border: none;")
        layout.addWidget(self.explorer_title)
        
        self.explorer_subtitle = QLabel("Browse and search your indexed directories from the local cache.")
        self.explorer_subtitle.setTextFormat(Qt.PlainText)
        self.explorer_subtitle.setStyleSheet("color: #6e6e6e; font-size: 13px; background: transparent;")
        layout.addWidget(self.explorer_subtitle)

        layout.addSpacing(20)

        # Search bar row
        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search indexed files…")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.setFixedHeight(34)
        self.search_bar.setStyleSheet("""
            QLineEdit {
                background: #f5f5f5;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 0 10px;
                font-size: 13px;
                color: #1a1a1a;
            }
            QLineEdit:focus {
                background: #ffffff;
                border: 1px solid #0078d4;
            }
        """)

        self.target_scan_btn = QPushButton()
        self.target_scan_btn.setIcon(qta.icon("fa5s.sync", color="white"))
        self.target_scan_btn.setIconSize(QSize(14, 14))
        self.target_scan_btn.setFixedSize(34, 34)
        self.target_scan_btn.setToolTip("Index current folder recursively")
        self.target_scan_btn.setEnabled(False)
        self.target_scan_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4; border: none; border-radius: 4px;
            }
            QPushButton:hover { background-color: #0067b8; }
            QPushButton:pressed { background-color: #005a9e; }
            QPushButton:disabled { background-color: #bad6ef; }
        """)

        search_row.addWidget(self.search_bar, 1)
        search_row.addWidget(self.target_scan_btn)
        layout.addLayout(search_row)
        layout.addSpacing(10)

        # Explorer table (contains back button + breadcrumb + table internally)
        self.table = ExplorerTable()
        layout.addWidget(self.table, 1)

        layout.addSpacing(6)

        # Status row
        status_row = QHBoxLayout()
        self.status_label = QLabel("Ready — open Settings to configure directories.")
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        self.item_count_label = QLabel("")
        self.item_count_label.setTextFormat(Qt.PlainText)
        self.item_count_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        self.item_count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.item_count_label)
        layout.addLayout(status_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        return self.explorer_page

    # ── Page: Scan Now ────────────────────────────────────
    def _build_scan_page(self) -> QWidget:
        self.scan_page = QWidget()
        self.scan_page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self.scan_page)
        layout.setContentsMargins(40, 32, 40, 24)
        layout.setSpacing(0)

        self.scan_title = QLabel("Scan Now")
        self.scan_title.setFont(QFont("Segoe UI Variable Display", 22, QFont.Bold))
        self.scan_title.setStyleSheet("font-size: 24px; font-weight: 700; background: transparent; border: none;")
        layout.addWidget(self.scan_title)

        self.scan_desc = QLabel("Index selected directories and write metadata to the shared SQLite cache.")
        self.scan_desc.setTextFormat(Qt.PlainText)
        self.scan_desc.setStyleSheet("color: #6e6e6e; font-size: 13px; background: transparent;")
        layout.addWidget(self.scan_desc)
        layout.addSpacing(24)

        # Info banner
        self.scan_banner = QWidget()
        self.scan_banner.setStyleSheet("""
            QWidget {
                background-color: #eff6fc;
                border: 1px solid #cce4f7;
                border-radius: 6px;
            }
            QLabel { border: none; background: transparent; }
        """)
        banner_layout = QHBoxLayout(self.scan_banner)
        banner_layout.setContentsMargins(14, 10, 14, 10)
        banner_layout.setSpacing(10)
        b_icon = QLabel()
        b_icon.setPixmap(qta.icon("fa5s.info-circle", color="#0078d4").pixmap(QSize(16, 16)))
        self.scan_banner_text = QLabel(
            "Scanning runs entirely in the background using a worker thread. "
            "You can browse the Explorer while indexing."
        )
        self.scan_banner_text.setTextFormat(Qt.PlainText)
        self.scan_banner_text.setWordWrap(True)
        self.scan_banner_text.setStyleSheet("font-size: 13px; color: #1a1a1a;")
        banner_layout.addWidget(b_icon, 0, Qt.AlignTop)
        banner_layout.addWidget(self.scan_banner_text, 1)
        layout.addWidget(self.scan_banner)
        layout.addSpacing(20)

        # Scan card
        self.scan_action_card = QFrame()
        self.scan_action_card.setStyleSheet("""
            QFrame {
                background: #fafafa;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
            }
            QLabel { border: none; background: transparent; }
        """)
        cl = QVBoxLayout(self.scan_action_card)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(14)

        row = QHBoxLayout()
        row.setSpacing(14)
        s_icon = QLabel()
        s_icon.setPixmap(qta.icon("fa5s.hdd", color="#0078d4").pixmap(QSize(32, 32)))
        s_icon.setFixedSize(40, 40)
        s_icon.setAlignment(Qt.AlignCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        self.scan_card_title = QLabel("Full Recursive Scan")
        self.scan_card_title.setTextFormat(Qt.PlainText)
        self.scan_card_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #1a1a1a; background: transparent;")
        self.scan_card_desc = QLabel(
            "Traverses all configured directories recursively, extracts file metadata, "
            "and writes everything to the shared SQLite cache using batched transactions."
        )
        self.scan_card_desc.setTextFormat(Qt.PlainText)
        self.scan_card_desc.setWordWrap(True)
        self.scan_card_desc.setStyleSheet("font-size: 12px; color: #6e6e6e; background: transparent;")
        text_col.addWidget(self.scan_card_title)
        text_col.addWidget(self.scan_card_desc)
        row.addWidget(s_icon, 0, Qt.AlignTop)
        row.addLayout(text_col, 1)
        cl.addLayout(row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #e5e5e5;")
        cl.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.scan_btn = QPushButton("Start Full Scan")
        self.scan_btn.setFixedHeight(32)
        self.scan_btn.setStyleSheet("""
            QPushButton {
                background: #0078d4; color: #ffffff;
                border: none; border-radius: 4px;
                font-size: 13px; font-weight: 600; padding: 0 18px;
            }
            QPushButton:hover { background: #0067b8; }
            QPushButton:pressed { background: #005a9e; }
            QPushButton:disabled { background: #bad6ef; }
        """)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedHeight(32)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #c8c8c8; border-radius: 4px;
                font-size: 13px; padding: 0 16px;
            }
        """)

        btn_row.addWidget(self.scan_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch()
        cl.addLayout(btn_row)

        self.scan_progress_bar = QProgressBar()
        self.scan_progress_bar.setRange(0, 0)
        self.scan_progress_bar.setFixedHeight(3)
        self.scan_progress_bar.setVisible(False)
        cl.addWidget(self.scan_progress_bar)

        self.scan_status_label = QLabel("")
        self.scan_status_label.setTextFormat(Qt.PlainText)
        self.scan_status_label.setStyleSheet("font-size: 12px; background: transparent;")
        self.scan_status_label.setVisible(False)
        cl.addWidget(self.scan_status_label)

        layout.addWidget(self.scan_action_card)
        layout.addStretch()

        return self.scan_page

    # ── Public API ────────────────────────────────────────
    def set_status(self, text: str):
        self.status_label.setText(text)
        self.scan_status_label.setText(text)

    def set_progress(self, visible: bool, text: str = ""):
        self.progress_bar.setVisible(visible)
        self.scan_progress_bar.setVisible(visible)
        self.scan_status_label.setVisible(visible)
        self.cancel_btn.setVisible(visible)
        self.scan_btn.setEnabled(not visible)
        self.target_scan_btn.setEnabled(not visible)
        if text:
            self.set_status(text)

    def update_translations(self, t: dict):
        # Update NavButtons
        self.nav_explorer.setText(t["explorer"])
        self.nav_scan.setText(t["scan_now"])
        self.nav_settings.setText(t["settings"])
        
        # Window Title
        self.setWindowTitle(f"DirCache Explorer v1.1.0 - {t['explorer']}")
        self.title_label.setText(f"DirCache Explorer - {t['explorer']}")

        # Explorer Page
        self.search_bar.setPlaceholderText(t["search_placeholder"])
        self.explorer_title.setText(t["explorer"])
        self.explorer_subtitle.setText("Browse and search your indexed directories from the local cache.") # This one is static for now or can be translated if key exists
        
        # Scan Page
        self.scan_title.setText(t["scan_now"])
        self.scan_desc.setText(t["scan_desc"])
        self.scan_banner_text.setText(t["scan_banner"])
        self.scan_card_title.setText(t["full_recursive_scan"])
        self.scan_btn.setText(t["start_full_scan"])
        self.cancel_btn.setText(t["cancel"])
        
        # Settings Page
        self.settings_panel.update_translations(t)

    def set_theme(self, is_dark: bool):
        bg = "#1e1e1e" if is_dark else "#ffffff"
        fg = "#ffffff" if is_dark else "#1a1a1a"
        sidebar = "#252525" if is_dark else "#f3f3f3"
        border = "#333333" if is_dark else "#ebebeb"
        subtext = "#aaaaaa" if is_dark else "#666666"
        card = "#2d2d2d" if is_dark else "#fafafa"
        
        self.central_widget.setStyleSheet(f"""
            #MainWindowContent {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {'0px' if self.isFullScreen() else '8px'};
            }}
        """)
        
        self.sidebar_widget.setStyleSheet(f"""
            #Sidebar {{
                background: {sidebar};
                border-right: 1px solid {border};
                border-bottom-left-radius: {'0px' if self.isFullScreen() else '8px'};
            }}
        """)
        
        self.stack.setStyleSheet(f"background: {bg}; border: none;")
        self.settings_scroll.setStyleSheet(f"background: {bg}; border: none;")
        
        self.title_bar.setStyleSheet(f"background: {sidebar};")
        self.title_label.setStyleSheet(f"color: {subtext}; font-size: 11px; background: transparent; border: none;")
        self.explorer_title.setStyleSheet(f"color: {fg}; background: transparent; border: none;")
        self.explorer_subtitle.setStyleSheet(f"color: {subtext}; background: transparent; border: none;")
        self.scan_title.setStyleSheet(f"color: {fg}; background: transparent; border: none;")
        self.scan_desc.setStyleSheet(f"color: {subtext}; background: transparent; border: none;")
        
        # Scan page specific themes
        banner_bg = "#1f2937" if is_dark else "#eff6fc" # Dark slate blue
        banner_border = "#374151" if is_dark else "#cce4f7"
        self.scan_banner.setStyleSheet(f"QWidget {{ background-color: {banner_bg}; border: 1px solid {banner_border}; border-radius: 6px; }} QLabel {{ border: none; background: transparent; color: {fg}; }}")
        if hasattr(self, 'scan_banner_text'):
            self.scan_banner_text.setStyleSheet(f"font-size: 13px; color: {fg}; background: transparent; border: none;")
        
        self.scan_action_card.setStyleSheet(f"QFrame {{ background: {card}; border: 1px solid {border}; border-radius: 8px; }} QLabel {{ border: none; background: transparent; color: {fg}; }}")
        if hasattr(self, 'scan_card_title'):
            self.scan_card_title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {fg}; background: transparent; border: none;")
        if hasattr(self, 'scan_card_desc'):
            self.scan_card_desc.setStyleSheet(f"font-size: 12px; color: {subtext}; background: transparent; border: none;")
        
        # Search bar theme
        self.search_bar.setStyleSheet(f"""
            QLineEdit {{
                background: {card};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 0 10px;
                font-size: 13px;
                color: {fg};
            }}
            QLineEdit:focus {{
                background: {bg};
                border: 1px solid #0078d4;
            }}
        """)
        
        # Sidebar text/icons (handled by NavButton but we can force refresh)
        self.app_logo_lbl.setStyleSheet(f"color: {fg}; background: transparent; border: none;")
        for btn in self._nav_btns:
            btn.is_dark = is_dark
            btn._apply(btn._active)

        # Propagate theme to sub-widgets
        self.table.set_theme(is_dark)
        self.settings_panel.set_theme(is_dark)

        # Update main buttons
        btn_fg = "#ffffff" if is_dark else "#1a1a1a"
        hover_bg = "rgba(255,255,255,0.1)" if is_dark else "rgba(0,0,0,0.05)"
        btn_style = f"QPushButton {{ color: {btn_fg}; background: transparent; border: none; width: 46px; height: 32px; }} QPushButton:hover {{ background: {hover_bg}; }}"
        self.min_btn.setStyleSheet(btn_style)
        self.max_btn.setStyleSheet(btn_style)
        self.close_btn.setStyleSheet(btn_style + " QPushButton:hover { background: #c42b1c; color: white; }")

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            is_full = self.isFullScreen()
            self.title_bar.setVisible(not is_full)
            # Re-apply theme to fix border radius
            self.set_theme(self.is_dark_mode())
        super().changeEvent(event)

    def is_dark_mode(self) -> bool:
        # Check current settings to determine if we should be in dark mode
        settings = self.settings_panel.get_settings()
        theme = settings.get("theme", "System Default")
        if theme == "System Default":
            from PySide6.QtGui import QPalette
            return QPalette().window().color().lightness() < 128
        return theme == "Dark"

    def show_properties(self):
        # Trigger properties for currently selected item in table
        self.table._on_context_properties()

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            self.max_btn.setText("▢")
        else:
            self.showMaximized()
            self.max_btn.setText("❐")


    # ── Window Dragging ───────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < 32:
            self._is_dragging = True
            self._drag_start_pos = event.globalPosition().toPoint()
            self._window_start_pos = self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if hasattr(self, "_is_dragging") and self._is_dragging:
            delta = event.globalPosition().toPoint() - self._drag_start_pos
            self.move(self._window_start_pos + delta)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._is_dragging = False
