from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QPushButton, QLabel, QLineEdit,
    QProgressBar, QFrame, QSizePolicy, QScrollArea
)
from PySide6.QtCore import Qt, QSize
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
    def __init__(self, label: str, icon_name: str, icon_color: str,
                 on_click, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._on_click = on_click
        self._active = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(12)

        # Active indicator (blue pill)
        self._indicator = QFrame()
        self._indicator.setFixedSize(3, 16)
        self._indicator.setStyleSheet("background-color: transparent; border-radius: 1.5px;")

        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(16, 16)
        self._active_icon   = qta.icon(icon_name, color=icon_color).pixmap(QSize(16, 16))
        self._inactive_icon = qta.icon(icon_name, color="#1a1a1a").pixmap(QSize(16, 16))
        self._icon_lbl.setPixmap(self._inactive_icon)
        self._icon_lbl.setAlignment(Qt.AlignCenter)

        self._text_lbl = QLabel(label)
        self._text_lbl.setFont(QFont("Segoe UI Variable Text", 10))
        self._text_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout.addWidget(self._indicator, 0, Qt.AlignVCenter)
        layout.addSpacing(6) # More space after indicator for better indent
        layout.addWidget(self._icon_lbl)
        layout.addWidget(self._text_lbl)
        self._apply(False)

    # ── state ──────────────────────────────────────────────
    def set_active(self, active: bool):
        self._active = active
        self._apply(active)

    def _apply(self, active: bool):
        if active:
            self.setStyleSheet("NavButton { background-color: #ebebeb; border-radius: 4px; border: none; }")
            self._indicator.setStyleSheet("background-color: #0078d4; border-radius: 1.5px; border: none;")
            self._icon_lbl.setPixmap(self._active_icon)
            self._icon_lbl.setStyleSheet("border: none; background: transparent;")
            self._text_lbl.setStyleSheet("color: #1a1a1a; font-weight: 600; background: transparent; border: none;")
        else:
            self.setStyleSheet("NavButton { background-color: transparent; border-radius: 4px; border: none; }")
            self._indicator.setStyleSheet("background-color: transparent; border: none;")
            self._icon_lbl.setPixmap(self._inactive_icon)
            self._icon_lbl.setStyleSheet("border: none; background: transparent;")
            self._text_lbl.setStyleSheet("color: #1a1a1a; font-weight: 400; background: transparent; border: none;")

    # ── events ─────────────────────────────────────────────
    def mousePressEvent(self, _):
        self._on_click()

    def enterEvent(self, _):
        if not self._active:
            self.setStyleSheet("NavButton { background-color: #f0f0f0; border-radius: 4px; }")

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
        self.resize(1080, 720)
        self.setMinimumSize(820, 560)
        self.setStyleSheet(STYLESHEET)

        root = QWidget()
        root.setStyleSheet("background: #ffffff;")
        self.setCentralWidget(root)

        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Sidebar ───────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("background-color: #f9f9f9; border-right: 1px solid #e5e5e5;")
        sb_layout = QVBoxLayout(sidebar)
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
        app_name_lbl = QLabel("DirCache")
        app_name_lbl.setFont(QFont("Segoe UI Variable Display", 12, QFont.Bold))
        app_name_lbl.setStyleSheet("color: #1a1a1a; background: transparent; border: none;")
        ar_layout.addWidget(app_icon_lbl)
        ar_layout.addWidget(app_name_lbl)
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

        self._add_nav(nav_layout, "Explorer",  "fa5s.folder-open", "#0078d4", 0)
        self._add_nav(nav_layout, "Scan Now",  "fa5s.search",      "#107c10", 1)
        nav_layout.addSpacing(6)
        nav_layout.addWidget(_h_sep())
        nav_layout.addWidget(_section_label("Configure"))
        self._add_nav(nav_layout, "Settings",  "fa5s.cog",         "#6b69d6", 2)
        nav_layout.addStretch()

        sb_layout.addWidget(nav_pad, 1)
        sb_layout.addWidget(_h_sep())

        # Bottom static items
        bottom_pad = QWidget()
        bottom_pad.setStyleSheet("background: transparent;")
        bot_layout = QVBoxLayout(bottom_pad)
        bot_layout.setContentsMargins(6, 6, 6, 8)
        bot_layout.setSpacing(2)

        version_lbl = QLabel("DirCache v1.0.0 Stable")
        version_lbl.setStyleSheet("color: #aaaaaa; font-size: 11px; padding-left: 14px; background: transparent; border: none;")
        bot_layout.addWidget(version_lbl)

        sb_layout.addWidget(bottom_pad)

        # ── Content Stack ─────────────────────────────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: #ffffff;")

        self.stack.addWidget(self._build_explorer_page())
        self.stack.addWidget(self._build_scan_page())

        settings_scroll = QScrollArea()
        settings_scroll.setWidget(SettingsPanel())
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.NoFrame)
        settings_scroll.setStyleSheet("background: #ffffff;")
        self.settings_panel = settings_scroll.widget()
        self.stack.addWidget(settings_scroll)

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self.stack, 1)

        # Activate first
        self._nav_btns[0].set_active(True)

    # ── Nav helper ────────────────────────────────────────
    def _add_nav(self, layout, label, icon, color, index):
        btn = NavButton(label, icon, color, lambda idx=index: self._navigate(idx))
        self._nav_btns.append(btn)
        layout.addWidget(btn)

    def _navigate(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_btns):
            btn.set_active(i == index)

    # ── Page: Explorer ────────────────────────────────────
    def _build_explorer_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: #ffffff;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 32, 40, 16)
        layout.setSpacing(0)

        # Title
        title = QLabel("File Explorer")
        title.setTextFormat(Qt.PlainText)
        title.setFont(QFont("Segoe UI Variable Display", 20, QFont.Bold))
        title.setStyleSheet("color: #1a1a1a; margin-bottom: 2px; background: transparent;")
        layout.addWidget(title)

        subtitle = QLabel("Browse and search your indexed directories from the local cache.")
        subtitle.setTextFormat(Qt.PlainText)
        subtitle.setStyleSheet("color: #6e6e6e; font-size: 13px; background: transparent;")
        layout.addWidget(subtitle)

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

        return page

    # ── Page: Scan Now ────────────────────────────────────
    def _build_scan_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: #ffffff;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 32, 40, 24)
        layout.setSpacing(0)

        title = QLabel("Scan Now")
        title.setTextFormat(Qt.PlainText)
        title.setFont(QFont("Segoe UI Variable Display", 20, QFont.Bold))
        title.setStyleSheet("color: #1a1a1a; background: transparent;")
        layout.addWidget(title)

        subtitle = QLabel("Index selected directories and write metadata to the shared SQLite cache.")
        subtitle.setTextFormat(Qt.PlainText)
        subtitle.setStyleSheet("color: #6e6e6e; font-size: 13px; background: transparent;")
        layout.addWidget(subtitle)
        layout.addSpacing(24)

        # Info banner
        banner = QWidget()
        banner.setStyleSheet("""
            QWidget {
                background-color: #eff6fc;
                border: 1px solid #cce4f7;
                border-radius: 6px;
            }
            QLabel { border: none; background: transparent; }
        """)
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(14, 10, 14, 10)
        banner_layout.setSpacing(10)
        b_icon = QLabel()
        b_icon.setPixmap(qta.icon("fa5s.info-circle", color="#0078d4").pixmap(QSize(16, 16)))
        b_text = QLabel(
            "Scanning runs entirely in the background using a worker thread. "
            "The UI stays responsive. You can browse the Explorer while indexing."
        )
        b_text.setTextFormat(Qt.PlainText)
        b_text.setWordWrap(True)
        b_text.setStyleSheet("font-size: 13px; color: #1a1a1a;")
        banner_layout.addWidget(b_icon, 0, Qt.AlignTop)
        banner_layout.addWidget(b_text, 1)
        layout.addWidget(banner)
        layout.addSpacing(20)

        # Scan card
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #fafafa;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
            }
            QLabel { border: none; background: transparent; }
        """)
        cl = QVBoxLayout(card)
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
        s_title = QLabel("Full Recursive Scan")
        s_title.setTextFormat(Qt.PlainText)
        s_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #1a1a1a; background: transparent;")
        s_desc = QLabel(
            "Traverses all configured directories recursively, extracts file metadata, "
            "and writes everything to the shared SQLite cache using batched transactions."
        )
        s_desc.setTextFormat(Qt.PlainText)
        s_desc.setWordWrap(True)
        s_desc.setStyleSheet("font-size: 12px; color: #6e6e6e; background: transparent;")
        text_col.addWidget(s_title)
        text_col.addWidget(s_desc)
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
                background: #ffffff; color: #1a1a1a;
                border: 1px solid #c8c8c8; border-radius: 4px;
                font-size: 13px; padding: 0 16px;
            }
            QPushButton:hover { background: #f5f5f5; }
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
        self.scan_status_label.setStyleSheet("font-size: 12px; color: #6e6e6e; background: transparent;")
        self.scan_status_label.setVisible(False)
        cl.addWidget(self.scan_status_label)

        layout.addWidget(card)
        layout.addStretch()

        return page

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
