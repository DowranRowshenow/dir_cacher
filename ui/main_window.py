import datetime
from PySide6.QtCore import (
    Qt,
    QSize,
    Signal,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
    QEvent,
    QPoint,
)

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QPushButton,
    QLabel,
    QLineEdit,
    QProgressBar,
    QFrame,
    QSizePolicy,
    QScrollArea,
    QCheckBox,
    QComboBox,
    QMenu,
    QWidgetAction,
    QApplication,
)
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
    def __init__(self, label: str, icon: str, icon_color: str, on_click, parent=None):
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
        self._indicator.setStyleSheet(
            "background-color: transparent; border-radius: 1.5px;"
        )

        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(20, 20)
        self._icon_lbl.setStyleSheet("border: none; background: transparent;")

        self._text_lbl = QLabel(label)
        self._text_lbl.setFont(QFont("Segoe UI Variable Display", 10))
        self._text_lbl.setStyleSheet(
            "color: #aaaaaa; background: transparent; border: none;"
        )

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
            self.setStyleSheet(
                f"NavButton {{ background-color: {bg}; border-radius: 4px; border: none; }}"
            )
            self._indicator.setStyleSheet(
                "background-color: #0078d4; border-radius: 1.5px; border: none;"
            )
            self._icon_lbl.setPixmap(self._colored_icon)
            self._text_lbl.setStyleSheet(
                f"color: {fg}; font-weight: 600; background: transparent; border: none;"
            )
        else:
            self.setStyleSheet(
                f"NavButton {{ background-color: transparent; border-radius: 4px; border: none; }}"
            )
            self._indicator.setStyleSheet(
                "background-color: transparent; border: none;"
            )
            self._icon_lbl.setPixmap(self._inactive_icon)
            self._text_lbl.setStyleSheet(
                "color: #aaaaaa; font-weight: 400; background: transparent; border: none;"
            )

    def setText(self, text: str):
        self._text_lbl.setText(text)

    # ── events ─────────────────────────────────────────────
    def mousePressEvent(self, _):
        self._on_click()

    def enterEvent(self, _):
        if not self._active:
            hover_bg = "rgba(255,255,255,0.1)" if self.is_dark else "#e5e5e5"
            self.setStyleSheet(
                f"NavButton {{ background-color: {hover_bg}; border-radius: 4px; }}"
            )

    def leaveEvent(self, _):
        self._apply(self._active)


def _h_sep() -> QFrame:
    f = QFrame()
    f.setObjectName("HSep")
    f.setFrameShape(QFrame.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet("background-color: #e5e5e5; border: none; margin: 0 12px;")
    return f


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setFont(QFont("Segoe UI Variable Text", 8, QFont.Bold))
    lbl.setStyleSheet(
        "color: #888888; padding: 6px 14px 2px 14px; letter-spacing: 0.8px; background: transparent; border: none;"
    )
    return lbl


# ──────────────────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    dir_scan_requested = Signal(str)
    dir_cancel_requested = Signal(str)
    dir_pause_requested = Signal(str, bool)
    filter_changed = Signal()
    closed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DirCache Explorer")
        self.dir_ui_map = {}
        self.is_dark = False
        self.setWindowFlags(Qt.Window)
        self.resize(1080, 720)
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(STYLESHEET)
        self._generate_checkbox_icons()
        self.custom_date_range = None  # (start_ts, end_ts)

        self.central_widget = QWidget()
        self.central_widget.setObjectName("MainWindowContent")
        self.central_widget.setStyleSheet(
            """
            #MainWindowContent { background: #ffffff; }
        """
        )
        self.setCentralWidget(self.central_widget)

        layout = QVBoxLayout(self.central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Sidebar & Stack ───────────────────────────────
        content_row = QWidget()
        root_layout = QHBoxLayout(content_row)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        layout.addWidget(content_row, 1)

        self.sidebar_widget = QWidget()
        self.sidebar_widget.setObjectName("Sidebar")
        self.sidebar_widget.setFixedWidth(240)
        self.sidebar_widget.setStyleSheet(
            "background: #f3f3f3; border-right: 1px solid #ebebeb;"
        )
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
        app_icon_lbl.setPixmap(
            QPixmap("assets/logo.png").scaled(
                18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )
        app_icon_lbl.setStyleSheet("border: none;")
        self.app_logo_lbl = QLabel("DirCache")
        self.app_logo_lbl.setFont(QFont("Segoe UI Variable Display", 12, QFont.Bold))
        self.app_logo_lbl.setStyleSheet(
            "color: #1a1a1a; background: transparent; border: none;"
        )
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

        self.nav_explorer = self._add_nav(
            nav_layout, "Explorer", "fa5s.folder-open", "#0078d4", 0
        )
        self.nav_scan = self._add_nav(
            nav_layout, "Scan Now", "fa5s.search", "#107c10", 1
        )
        nav_layout.addSpacing(6)
        nav_layout.addWidget(_h_sep())
        nav_layout.addWidget(_section_label("Configure"))
        self.nav_settings = self._add_nav(
            nav_layout, "Settings", "fa5s.cog", "#6b69d6", 2
        )
        nav_layout.addStretch()

        sb_layout.addWidget(nav_pad, 1)
        sb_layout.addWidget(_h_sep())

        # Bottom static items
        bottom_pad = QWidget()
        bottom_pad.setStyleSheet("background: transparent;")
        bot_layout = QVBoxLayout(bottom_pad)
        bot_layout.setContentsMargins(6, 6, 6, 8)
        bot_layout.setSpacing(2)

        version_lbl = QLabel("DirCache v1.0")
        version_lbl.setStyleSheet(
            "color: #aaaaaa; font-size: 11px; padding-left: 14px; background: transparent; border: none;"
        )

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
        self.settings_panel.text_context_menu_requested.connect(
            self._create_text_context_menu
        )
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

    def _generate_checkbox_icons(self):
        """Generate checkmark images for the stylesheet since we can't use qta directly in CSS."""
        try:
            # Generate a blue checkmark
            icon = qta.icon("fa5s.check", color="#0078d4")
            pix = icon.pixmap(QSize(12, 12))
            pix.save("assets/check_blue.png")

            # Generate a white checkmark
            icon_w = qta.icon("fa5s.check", color="#ffffff")
            pix_w = icon_w.pixmap(QSize(12, 12))
            pix_w.save("assets/check_white.png")
        except Exception:
            pass

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
        self.explorer_title.setStyleSheet(
            "font-size: 24px; font-weight: 700; background: transparent; border: none;"
        )
        layout.addWidget(self.explorer_title)

        self.explorer_subtitle = QLabel(
            "Browse and search your indexed directories from the local cache."
        )
        self.explorer_subtitle.setTextFormat(Qt.PlainText)
        self.explorer_subtitle.setStyleSheet(
            "color: #6e6e6e; font-size: 13px; background: transparent;"
        )

        # Add global spinner to title row
        title_row = QHBoxLayout()
        title_row.addWidget(self.explorer_title)
        title_row.addStretch()
        self.global_spinner = QLabel()
        self.global_spinner.setFixedSize(24, 24)
        title_row.addWidget(self.global_spinner)
        layout.addLayout(title_row)
        layout.addWidget(self.explorer_subtitle)

        layout.addSpacing(20)

        # Search bar row
        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search indexed files…")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.setFixedHeight(34)
        self.search_bar.setStyleSheet(
            """
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
        """
        )

        self.search_bar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.search_bar.customContextMenuRequested.connect(
            lambda pos: self._create_text_context_menu(self.search_bar, pos)
        )

        search_row.addWidget(self.search_bar, 4)

        self.search_shared_cb = QCheckBox("Shared")
        self.location_btn = QPushButton("All Locations")
        self.location_btn.setFixedWidth(130)
        self.location_btn.setCursor(Qt.PointingHandCursor)
        self.location_menu = QMenu(self)
        self.location_btn.setMenu(self.location_menu)
        self.location_checkboxes = {}
        search_row.addWidget(self.location_btn)

        self.case_sensitive_cb = QCheckBox("Aa")
        self.case_sensitive_cb.setFixedWidth(46)
        self.case_sensitive_cb.setToolTip("Match Case")
        self.case_sensitive_cb.setStyleSheet(
            """
            QCheckBox { font-size: 11px; color: #6e6e6e; background: transparent; padding: 0 4px; }
            QCheckBox::indicator {
                width: 14px; height: 14px;
                border: 1px solid #c8c8c8;
                border-radius: 3px;
                background: transparent;
            }
            QCheckBox::indicator:checked {
                border: 1px solid #0078d4;
                image: url(assets/check_blue.png);
            }
            QCheckBox::indicator:hover { border-color: #0078d4; }
        """
        )
        self.case_sensitive_cb.stateChanged.connect(
            lambda _: self._on_filter_changed(None)
        )
        search_row.addWidget(self.case_sensitive_cb)

        self.target_scan_btn = QPushButton()
        self.target_scan_btn.setIcon(qta.icon("fa5s.sync", color="white"))
        self.target_scan_btn.setIconSize(QSize(14, 14))
        self.target_scan_btn.setFixedSize(34, 34)
        self.target_scan_btn.setToolTip("Index current folder recursively")
        self.target_scan_btn.setEnabled(False)
        self.target_scan_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #0078d4; border: none; border-radius: 4px;
            }
            QPushButton:hover { background-color: #0067b8; }
            QPushButton:pressed { background-color: #005a9e; }
            QPushButton:disabled { background-color: #bad6ef; }
        """
        )

        search_row.addWidget(self.target_scan_btn)

        self.export_btn = QPushButton()
        self.export_btn.setIcon(qta.icon("fa5s.file-export", color="white"))
        self.export_btn.setIconSize(QSize(14, 14))
        self.export_btn.setFixedSize(34, 34)
        self.export_btn.setToolTip("Export Wizard")
        self.export_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #107c10; border: none; border-radius: 4px;
            }
            QPushButton:hover { background-color: #0b5a0b; }
            QPushButton:pressed { background-color: #094509; }
        """
        )
        search_row.addWidget(self.export_btn)
        layout.addLayout(search_row)
        layout.addSpacing(10)

        # ── Filter Bar ────────────────────────────────────
        self.filter_bar = QHBoxLayout()
        self.filter_bar.setSpacing(10)

        lbl_style = "color: #6e6e6e; font-size: 12px; font-weight: 500;"

        type_lbl = QLabel("Filter:")
        type_lbl.setStyleSheet(lbl_style)
        self.filter_bar.addWidget(type_lbl)

        # Multi-select dropdown button
        self.type_btn = QPushButton("Select Types")
        self.type_btn.setFixedWidth(140)
        self.type_btn.setCursor(Qt.PointingHandCursor)

        self.type_menu = QMenu(self)
        self.type_checkboxes = {}
        types = [
            "Text Files",
            "Excel",
            "Word",
            "PDF",
            "Drawings",
            "Images",
            "Music",
            "Videos",
            "Archives",
            "Executables",
        ]
        for t in types:
            action = QWidgetAction(self.type_menu)
            cb = QCheckBox(t)
            cb.setStyleSheet("padding: 4px 10px; color: inherit;")
            cb.stateChanged.connect(lambda _: self._on_filter_changed(None))
            cb.stateChanged.connect(self._update_type_btn_text)
            action.setDefaultWidget(cb)
            self.type_menu.addAction(action)
            self.type_checkboxes[t] = cb

        self.type_btn.setMenu(self.type_menu)
        self.filter_bar.addWidget(self.type_btn)

        self.filter_bar.addSpacing(20)

        date_lbl = QLabel("Date:")
        date_lbl.setStyleSheet(lbl_style)
        self.filter_bar.addWidget(date_lbl)

        self.date_filter = QComboBox()
        self.date_filter.setFixedWidth(120)
        self.date_filter.addItems(
            [
                "Any Time",
                "Today",
                "Last week",
                "Last month",
                "This Year",
                "Custom Range...",
            ]
        )
        self.date_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.filter_bar.addWidget(self.date_filter)

        self.filter_bar.addSpacing(20)

        self.clear_filters_btn = QPushButton("Clear All")
        self.clear_filters_btn.setFixedWidth(80)
        self.clear_filters_btn.setCursor(Qt.PointingHandCursor)
        self.clear_filters_btn.clicked.connect(self._clear_all_filters)
        self.filter_bar.addWidget(self.clear_filters_btn)

        self.filter_bar.addStretch()

        layout.addLayout(self.filter_bar)
        layout.addSpacing(10)

        # Explorer table (contains back button + breadcrumb + table internally)
        self.table = ExplorerTable()
        layout.addWidget(self.table, 1)

        layout.addSpacing(6)

        # Status row
        status_row = QHBoxLayout()
        self.status_label = QLabel("Ready — open Settings to configure directories.")
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setStyleSheet(
            "color: #888888; font-size: 12px; background: transparent;"
        )
        self.item_count_label = QLabel("")
        self.item_count_label.setTextFormat(Qt.PlainText)
        self.item_count_label.setStyleSheet(
            "color: #888888; font-size: 12px; background: transparent;"
        )
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

    def shutdown(self):
        """Safe shutdown of all background processes and database connections."""
        print("Shutting down DirCache...")
        # 1. Stop all active scanners
        for path, scanner in list(self.active_scanners.items()):
            print(f"Stopping scanner for: {path}")
            scanner.stop_scan()
        self.active_scanners.clear()

        # 2. Stop search worker if running
        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.stop()
            self.search_worker.wait()

        # 3. Close database connections
        if self.local_db:
            print("Closing local database...")
            self.local_db.close()
            self.local_db = None
        if self.shared_db:
            print("Closing shared database...")
            self.shared_db.close()
            self.shared_db = None

    def _clear_all_filters(self):
        self.search_bar.clear()
        for cb in self.type_checkboxes.values():
            cb.setChecked(False)
        self.date_filter.setCurrentIndex(0)
        # We don't clear location checkboxes, they should default to checked
        self._on_filter_changed(None)

    def _on_filter_changed(self, _):
        self.filter_changed.emit()

    def _create_text_context_menu(self, line_edit: QLineEdit, pos: QPoint):
        from ui.i18n import TRANSLATIONS

        lang = self.settings_panel.lang_combo.currentData() or "en"
        t = TRANSLATIONS.get(lang, TRANSLATIONS["en"])

        is_dark = self.is_dark
        icon_blue = "#0078d4"
        icon_red = "#c42b1c"
        icon_gray = "#aaaaaa" if is_dark else "#666666"

        menu = QMenu(self)

        # Standard QLineEdit actions with modern Phosphor icons and translations
        undo_act = menu.addAction(
            qta.icon("ph.arrow-counter-clockwise", color=icon_blue), t["undo"]
        )
        undo_act.setEnabled(line_edit.isUndoAvailable())
        undo_act.setShortcut("Ctrl+Z")
        undo_act.triggered.connect(line_edit.undo)

        redo_act = menu.addAction(
            qta.icon("ph.arrow-clockwise", color=icon_blue), t["redo"]
        )
        redo_act.setEnabled(line_edit.isRedoAvailable())
        redo_act.setShortcut("Ctrl+Y")
        redo_act.triggered.connect(line_edit.redo)

        menu.addSeparator()

        cut_act = menu.addAction(qta.icon("ph.scissors", color=icon_gray), t["cut"])
        cut_act.setEnabled(not line_edit.isReadOnly() and line_edit.hasSelectedText())
        cut_act.setShortcut("Ctrl+X")
        cut_act.triggered.connect(line_edit.cut)

        copy_act = menu.addAction(qta.icon("ph.copy", color=icon_gray), t["copy"])
        copy_act.setEnabled(line_edit.hasSelectedText())
        copy_act.setShortcut("Ctrl+C")
        copy_act.triggered.connect(line_edit.copy)

        paste_act = menu.addAction(
            qta.icon("ph.clipboard-text", color=icon_gray), t["paste"]
        )
        paste_act.setEnabled(
            not line_edit.isReadOnly() and QApplication.clipboard().text() != ""
        )
        paste_act.setShortcut("Ctrl+V")
        paste_act.triggered.connect(line_edit.paste)

        delete_act = menu.addAction(qta.icon("ph.trash", color=icon_red), t["delete"])
        delete_act.setEnabled(
            not line_edit.isReadOnly() and line_edit.hasSelectedText()
        )
        delete_act.triggered.connect(
            lambda: line_edit.insert("")
        )  # standard delete behavior
        delete_act.setShortcut("Del")

        menu.addSeparator()

        select_all_act = menu.addAction(
            qta.icon("ph.cursor", color=icon_gray), t["select_all"]
        )
        select_all_act.setShortcut("Ctrl+A")
        select_all_act.triggered.connect(line_edit.selectAll)

        menu.exec(line_edit.mapToGlobal(pos))

    def update_search_locations(self, scan_dirs: list[str]):
        self.location_menu.clear()
        self.location_checkboxes.clear()
        for d in scan_dirs:
            action = QWidgetAction(self.location_menu)
            import os

            cb = QCheckBox(os.path.basename(d.rstrip("/\\")) or d)
            cb.setToolTip(d)
            cb.setChecked(True)
            cb.setStyleSheet("padding: 4px 10px; color: inherit;")
            cb.stateChanged.connect(lambda _: self._on_filter_changed(None))
            cb.stateChanged.connect(self._update_location_btn_text)
            action.setDefaultWidget(cb)
            self.location_menu.addAction(action)
            self.location_checkboxes[d] = cb
        self._update_location_btn_text()

    def _update_location_btn_text(self, _=None):
        checked = [
            name for name, cb in self.location_checkboxes.items() if cb.isChecked()
        ]
        total = len(self.location_checkboxes)
        if total == 0:
            self.location_btn.setText("Locations")
        elif len(checked) == total:
            self.location_btn.setText("All Locations")
        elif len(checked) == 0:
            self.location_btn.setText("No Locations")
        elif len(checked) == 1:
            self.location_btn.setText("1 Location")
        else:
            self.location_btn.setText(f"{len(checked)} Locations")

    def _update_type_btn_text(self, _):
        checked = [name for name, cb in self.type_checkboxes.items() if cb.isChecked()]
        if not checked:
            self.type_btn.setText("Select Types")
        elif len(checked) == 1:
            self.type_btn.setText(checked[0])
        else:
            self.type_btn.setText(f"{len(checked)} types")

    def _on_filter_changed(self, index):
        txt = self.date_filter.currentText()
        last_idx = self.date_filter.count() - 1

        # Only show dialog if exactly "Custom Range..." is selected
        # (Once a range is set, the text is "DD.MM.YY - DD.MM.YY")
        if txt == "Custom Range...":
            self._show_custom_date_dialog()
        else:
            # If we are NOT on the custom range item, ensure it says "Custom Range..."
            if self.date_filter.currentIndex() != last_idx:
                if self.date_filter.itemText(last_idx) != "Custom Range...":
                    self.date_filter.blockSignals(True)
                    self.date_filter.setItemText(last_idx, "Custom Range...")
                    self.date_filter.blockSignals(False)

            # Emit signal to refresh view
            self.filter_changed.emit()

    def _show_custom_date_dialog(self):
        from PySide6.QtWidgets import QDialog, QDateEdit, QDialogButtonBox
        from PySide6.QtCore import QDate
        import datetime

        dlg = QDialog(self)
        dlg.setWindowTitle("Select Date Range")
        dlg.setFixedWidth(300)

        # Apply current theme to dialog
        is_dark = getattr(self, "is_dark", False)
        bg = "#252525" if is_dark else "#ffffff"
        fg = "#ffffff" if is_dark else "#1a1a1a"
        border = "#3d3d3d" if is_dark else "#cccccc"

        dlg.setStyleSheet(
            f"""
            QDialog {{ background-color: {bg}; color: {fg}; }}
            QLabel {{ color: {fg}; font-size: 13px; }}
            QDateEdit {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px;
            }}
            QPushButton {{
                background-color: {'#3d3d3d' if is_dark else '#f0f0f0'};
                color: {fg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 6px 16px;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {'#505050' if is_dark else '#e0e0e0'};
            }}
            QCalendarWidget QWidget {{ background-color: {bg}; color: {fg}; }}
            QCalendarWidget QAbstractItemView:enabled {{ color: {fg}; selection-background-color: #0078d4; }}
        """
        )

        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel("Start Date:"))
        self.start_edit = QDateEdit(QDate.currentDate().addDays(-7))
        self.start_edit.setCalendarPopup(True)
        layout.addWidget(self.start_edit)

        layout.addSpacing(10)
        layout.addWidget(QLabel("End Date:"))
        self.end_edit = QDateEdit(QDate.currentDate())
        self.end_edit.setCalendarPopup(True)
        layout.addWidget(self.end_edit)

        layout.addSpacing(20)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec() == QDialog.Accepted:
            start_dt = datetime.datetime.combine(
                self.start_edit.date().toPython(), datetime.time.min
            )
            end_dt = datetime.datetime.combine(
                self.end_edit.date().toPython(), datetime.time.max
            )
            self.custom_date_range = (start_dt.timestamp(), end_dt.timestamp())

            # Update the last item text to show the range
            range_str = f"{self.start_edit.date().toString('dd.MM.yy')} - {self.end_edit.date().toString('dd.MM.yy')}"
            last_idx = self.date_filter.count() - 1
            self.date_filter.blockSignals(True)
            self.date_filter.setItemText(last_idx, range_str)
            self.date_filter.setCurrentIndex(last_idx)
            self.date_filter.blockSignals(False)
            self.filter_changed.emit()
        else:
            # If cancelled, revert to "Any Time" (index 0)
            self.date_filter.blockSignals(True)
            self.date_filter.setCurrentIndex(0)
            self.date_filter.blockSignals(False)
            self.filter_changed.emit()

    # ── Page: Scan Now ────────────────────────────────────
    def _build_scan_page(self) -> QWidget:
        self.scan_scroll = QScrollArea()
        self.scan_scroll.setWidgetResizable(True)
        self.scan_scroll.setFrameShape(QFrame.NoFrame)
        self.scan_scroll.setStyleSheet("background: transparent; border: none;")

        self.scan_page = QWidget()
        self.scan_page.setStyleSheet("background: transparent;")
        self.scan_scroll.setWidget(self.scan_page)

        layout = QVBoxLayout(self.scan_page)
        layout.setContentsMargins(40, 32, 40, 24)
        layout.setSpacing(0)

        self.scan_title = QLabel("Scan Now")
        self.scan_title.setFont(QFont("Segoe UI Variable Display", 22, QFont.Bold))
        self.scan_title.setStyleSheet(
            "font-size: 24px; font-weight: 700; background: transparent; border: none;"
        )
        layout.addWidget(self.scan_title)

        self.scan_desc = QLabel(
            "Index selected directories and write metadata to the shared SQLite cache."
        )
        self.scan_desc.setTextFormat(Qt.PlainText)
        self.scan_desc.setStyleSheet(
            "color: #6e6e6e; font-size: 13px; background: transparent;"
        )
        layout.addWidget(self.scan_desc)
        layout.addSpacing(24)

        # Info banner
        self.scan_banner = QWidget()
        self.scan_banner.setStyleSheet(
            """
            QWidget {
                background-color: #eff6fc;
                border: 1px solid #cce4f7;
                border-radius: 6px;
            }
            QLabel { border: none; background: transparent; }
        """
        )
        banner_layout = QHBoxLayout(self.scan_banner)
        banner_layout.setContentsMargins(14, 10, 14, 10)
        banner_layout.setSpacing(10)
        b_icon = QLabel()
        b_icon.setPixmap(
            qta.icon("fa5s.info-circle", color="#0078d4").pixmap(QSize(16, 16))
        )
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
        self.scan_action_card.setStyleSheet(
            """
            QFrame {
                background: #fafafa;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
            }
            QLabel { border: none; background: transparent; }
        """
        )
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
        self.scan_card_title.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #1a1a1a; background: transparent;"
        )
        self.scan_card_desc = QLabel(
            "Traverses all configured directories recursively, extracts file metadata, "
            "and writes everything to the shared SQLite cache using batched transactions."
        )
        self.scan_card_desc.setTextFormat(Qt.PlainText)
        self.scan_card_desc.setWordWrap(True)
        self.scan_card_desc.setStyleSheet(
            "font-size: 12px; color: #6e6e6e; background: transparent;"
        )
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
        self.scan_btn.setStyleSheet(
            """
            QPushButton {
                background: #0078d4; color: #ffffff;
                border: none; border-radius: 4px;
                font-size: 13px; font-weight: 600; padding: 0 18px;
            }
            QPushButton:hover { background: #0067b8; }
            QPushButton:pressed { background: #005a9e; }
            QPushButton:disabled { background: #bad6ef; }
        """
        )

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedHeight(32)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setStyleSheet(
            """
            QPushButton {
                border: 1px solid #c8c8c8; border-radius: 4px;
                font-size: 13px; padding: 0 16px;
            }
        """
        )

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
        self.scan_status_label.setObjectName("ScanStatusLabel")
        self.scan_status_label.setTextFormat(Qt.PlainText)
        self.scan_status_label.setVisible(False)
        cl.addWidget(self.scan_status_label)

        layout.addWidget(self.scan_action_card)
        layout.addSpacing(20)

        self.scan_dirs_container = QWidget()
        self.scan_dirs_container.setStyleSheet("background: transparent;")
        self.scan_dirs_layout = QVBoxLayout(self.scan_dirs_container)
        self.scan_dirs_layout.setContentsMargins(0, 0, 0, 0)
        self.scan_dirs_layout.setSpacing(10)
        layout.addWidget(self.scan_dirs_container)

        layout.addStretch()

        return self.scan_scroll

    def update_scan_dirs(self, dir_infos: list[dict]):
        # Clear existing items
        while self.scan_dirs_layout.count():
            item = self.scan_dirs_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not dir_infos:
            return

        title = QLabel("Individual Directory Scans")
        title.setObjectName("IndividualScanTitle")
        title.setFont(QFont("Segoe UI Variable Text", 14, QFont.Bold))
        self.scan_dirs_layout.addWidget(title)

        self.dir_ui_map.clear()

        for info in dir_infos:
            d = info.get("path")
            if not d:
                continue

            row = QFrame()
            row.setObjectName("IndividualScanCard")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 10, 14, 10)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)

            path_lbl = QLabel(d)
            path_lbl.setObjectName("ScanCardPath")

            from datetime import datetime

            last_scan_ts = info.get("last_scan")
            item_count = info.get("item_count", 0)

            if last_scan_ts:
                dt_str = datetime.fromtimestamp(last_scan_ts).strftime("%Y-%m-%d %H:%M")
                scan_info = f"Last scanned: {dt_str}  •  {item_count:,} items indexed"
            else:
                scan_info = f"Not scanned yet  •  {item_count:,} items indexed"

            last_lbl = QLabel(scan_info)
            last_lbl.setObjectName("ScanCardLast")

            text_col.addWidget(path_lbl)
            text_col.addWidget(last_lbl)

            btn = QPushButton("Scan")
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _, path=d: self._on_dir_btn_clicked(path))

            pause_btn = QPushButton("Pause")
            pause_btn.setObjectName("ScanCardPauseBtn")
            pause_btn.setFixedHeight(28)
            pause_btn.setVisible(False)
            pause_btn.clicked.connect(
                lambda _, path=d: self._on_pause_btn_clicked(path)
            )

            row_layout.addLayout(text_col, 1)
            row_layout.addWidget(pause_btn, 0)
            row_layout.addWidget(btn, 0)
            self.scan_dirs_layout.addWidget(row)

            self.dir_ui_map[d] = {
                "time_lbl": last_lbl,
                "btn": btn,
                "pause_btn": pause_btn,
            }

        # Apply current theme to newly created widgets
        self.set_theme(self.is_dark)

    def _on_dir_btn_clicked(self, path: str):
        btn = self.dir_ui_map[path]["btn"]
        if btn.text() == "Scan":
            self.dir_scan_requested.emit(path)
        else:
            self.dir_cancel_requested.emit(path)

    def _on_pause_btn_clicked(self, path: str):
        pause_btn = self.dir_ui_map[path]["pause_btn"]
        is_paused = pause_btn.text() == "Resume"
        # We want to pause if it's currently running, meaning is_paused is false.
        # But if it's "Resume", we want to unpause.
        if is_paused:
            pause_btn.setText("Pause")
            self.dir_pause_requested.emit(path, False)
        else:
            pause_btn.setText("Resume")
            self.dir_pause_requested.emit(path, True)

    def set_scanning(self, active: bool):
        if active:
            color = "#0078d4" if getattr(self, "is_dark", False) else "#005a9e"
            icon = qta.icon(
                "fa5s.spinner", color=color, animation=qta.Spin(self.global_spinner)
            )
            self.global_spinner.setPixmap(icon.pixmap(QSize(20, 20)))
        else:
            self.global_spinner.clear()

    def set_dir_scan_state(self, path: str, is_scanning: bool, message: str):
        if path not in self.dir_ui_map:
            return

        ui = self.dir_ui_map[path]
        ui["time_lbl"].setText(message)

        if is_scanning:
            ui["btn"].setText("Cancel")
            ui["pause_btn"].setVisible(True)
            # Apply cancel theme dynamically based on mode
            if self.is_dark:
                ui["btn"].setStyleSheet(
                    """
                    QPushButton {
                        background: #6b2828; border: 1px solid #8c3636; border-radius: 4px;
                        padding: 0 16px; font-weight: 500; color: #ffffff;
                    }
                    QPushButton:hover { background: #8c3636; }
                """
                )
                ui["pause_btn"].setStyleSheet(
                    """
                    QPushButton {
                        background: #444444; border: 1px solid #666666; border-radius: 4px;
                        padding: 0 16px; font-weight: 500; color: #ffffff;
                    }
                    QPushButton:hover { background: #555555; }
                """
                )
            else:
                ui["btn"].setStyleSheet(
                    """
                    QPushButton {
                        background: #ffebe9; border: 1px solid #fd8a8b; border-radius: 4px;
                        padding: 0 16px; font-weight: 500; color: #d1242f;
                    }
                    QPushButton:hover { background: #ffcecb; }
                """
                )
                ui["pause_btn"].setStyleSheet(
                    """
                    QPushButton {
                        background: #fff3cd; border: 1px solid #ffe69c; border-radius: 4px;
                        padding: 0 16px; font-weight: 500; color: #664d03;
                    }
                    QPushButton:hover { background: #ffe69c; }
                """
                )
        else:
            ui["btn"].setText("Scan")
            ui["pause_btn"].setVisible(False)
            ui["pause_btn"].setText("Pause")
            # The general theme update will restore the default button style,
            # but we force the standard one here so it doesn't stay red.
            self.set_theme(self.is_dark)

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
        self.nav_explorer.setText(t.get("explorer", "Explorer"))
        self.nav_scan.setText(t.get("scan_now", "Scan Now"))
        self.nav_settings.setText(t.get("settings", "Settings"))

        # Date Filters
        self.date_filter.blockSignals(True)
        self.date_filter.setItemText(0, t.get("date_any", "Any Time"))
        self.date_filter.setItemText(1, t.get("date_today", "Today"))
        self.date_filter.setItemText(2, t.get("date_last_week", "Last week"))
        self.date_filter.setItemText(3, t.get("date_last_month", "Last month"))
        self.date_filter.setItemText(4, t.get("date_this_year", "This Year"))
        self.date_filter.setItemText(5, t.get("date_custom", "Custom Range..."))
        self.date_filter.blockSignals(False)

        # Window Title
        self.setWindowTitle(f"DIRCACHE - {t['explorer']}")

        # Explorer Page
        self.search_bar.setPlaceholderText(t["search_placeholder"])
        self.search_shared_cb.setText(t["shared_search"])
        self.settings_panel.clear_cache_btn.setText(t["clear_cache"])
        self.explorer_title.setText(t["explorer"])
        self.explorer_subtitle.setText(
            "Browse and search your indexed directories from the local cache."
        )  # This one is static for now or can be translated if key exists

        # Scan Page
        self.scan_title.setText(t["scan_now"])
        self.scan_desc.setText(t["scan_desc"])
        self.scan_banner_text.setText(t["scan_banner"])
        self.scan_card_title.setText(t["full_recursive_scan"])
        self.scan_btn.setText(t["start_full_scan"])
        self.cancel_btn.setText(t["cancel"])
        self.table.update_translations(t)

        # Settings Page
        self.settings_panel.update_translations(t)

    def set_theme(self, is_dark: bool):
        self.is_dark = is_dark

        # Windows Dark Mode Title Bar Hack
        from ui.styles import apply_dark_title_bar

        bg = "#1e1e1e" if is_dark else "#ffffff"
        apply_dark_title_bar(self, is_dark, bg)

        bg = "#1e1e1e" if is_dark else "#ffffff"
        fg = "#ffffff" if is_dark else "#1a1a1a"
        sidebar = "#252525" if is_dark else "#f3f3f3"
        border = "#333333" if is_dark else "#ebebeb"
        subtext = "#aaaaaa" if is_dark else "#666666"
        card = "#2d2d2d" if is_dark else "#fafafa"
        header = "#252525" if is_dark else "#f3f3f3"
        btn_bg = "#333333" if is_dark else "#f0f0f0"

        tooltip_bg = "#2d2d2d" if is_dark else "#ffffff"
        tooltip_fg = "#ffffff" if is_dark else "#1a1a1a"
        tooltip_border = "#444444" if is_dark else "#cccccc"

        scroll_bg = "transparent"
        scroll_handle = "#555555" if is_dark else "#cccccc"
        scroll_hover = "#777777" if is_dark else "#aaaaaa"

        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QColor as _QColor, QPalette as _QPalette

        _palette = QApplication.instance().palette()
        _palette.setColor(_QPalette.ToolTipBase, _QColor(tooltip_bg))
        _palette.setColor(_QPalette.ToolTipText, _QColor(tooltip_fg))
        QApplication.instance().setPalette(_palette)
        QApplication.instance().setStyleSheet(
            f"""
            QToolTip {{
                background-color: {tooltip_bg};
                color: {tooltip_fg};
                border: 1px solid {tooltip_border};
                border-radius: 4px;
                padding: 6px 10px;
                margin: 2px;
                font-weight: 500;
            }}
            QDialog, QMessageBox, QInputDialog {{
                background-color: {bg};
                color: {fg};
            }}
            QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel {{
                background-color: {header};
                color: {fg};
                padding: 6px;
                border-bottom: 1px solid {border};
                font-weight: 600;
            }}
            QDialog QPushButton, QMessageBox QPushButton, QInputDialog QPushButton, QDialogButtonBox QPushButton {{
                background: {btn_bg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px 16px;
                color: {fg};
            }}
            QDialogButtonBox QPushButton {{
                padding: 4px 12px;
                border: 1px solid {border};
                border-radius: 4px;
                background: {'#333333' if is_dark else '#f0f0f0'};
                color: {fg};
            }}
            QDialogButtonBox QPushButton:hover {{
                background: {'#444444' if is_dark else '#e0e0e0'};
            }}
            QDialog QPushButton:hover, QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {{
                background: {'#444444' if is_dark else '#e0e0e0'};
            }}
            QDialog QLineEdit, QInputDialog QLineEdit {{
                background: {'#2d2d2d' if is_dark else '#ffffff'};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px;
                color: {fg};
            }}
            QMenu {{
                background-color: {card};
                border: 1px solid {border};
                padding: 4px;
                border-radius: 8px;
            }}
            QMenu::item {{
                padding: 6px 16px 6px 36px;
                border-radius: 4px;
                color: {fg};
            }}
            QMenu::item:selected {{
                background-color: {'#3d3d3d' if is_dark else '#f0f0f0'};
            }}
            QMenu::separator {{
                height: 1px;
                background: {border};
                margin: 4px 8px;
            }}
            #IndividualScanTitle {{ font-family: 'Segoe UI Variable Text', 'Inter', 'Segoe UI', sans-serif; color: {fg}; background: transparent; }}
            #ScanCardPath {{ font-size: 13px; color: {fg}; background: transparent; font-weight: 500; }}
            #ScanCardLast {{ font-size: 11px; color: {subtext}; background: transparent; }}
            #IndividualScanCard {{ background: {card}; border: none; border-radius: 6px; }}
            QScrollBar:vertical {{
                border: none;
                background: {scroll_bg};
                width: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {scroll_handle};
                min-height: 20px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {scroll_hover};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
            }}
            QScrollBar:horizontal {{
                border: none;
                background: {scroll_bg};
                height: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: {scroll_handle};
                min-width: 20px;
                border-radius: 5px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {scroll_hover};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                border: none;
                background: none;
            }}
        """
        )

        self.central_widget.setStyleSheet(f"#MainWindowContent {{ background: {bg}; }}")

        self.sidebar_widget.setStyleSheet(
            f"""
            #Sidebar {{
                background: {sidebar};
                border-right: 1px solid {border};
            }}
        """
        )

        # Dynamically style the horizontal separators in the sidebar
        sep_color = "#333333" if is_dark else "#e5e5e5"
        for sep in self.sidebar_widget.findChildren(QFrame):
            if sep.objectName() == "HSep":
                sep.setStyleSheet(
                    f"background-color: {sep_color}; border: none; margin: 0 12px;"
                )

        self.stack.setStyleSheet(f"background: {bg}; border: none;")
        self.settings_scroll.setStyleSheet(f"background: {bg}; border: none;")

        self.explorer_title.setStyleSheet(
            f"font-family: 'Segoe UI Variable Text', 'Inter', 'Segoe UI', sans-serif; color: {fg}; background: transparent; border: none;"
        )
        self.explorer_subtitle.setStyleSheet(
            f"color: {subtext}; background: transparent; border: none;"
        )
        self.scan_title.setStyleSheet(
            f"font-family: 'Segoe UI Variable Text', 'Inter', 'Segoe UI', sans-serif; color: {fg}; background: transparent; border: none;"
        )
        self.scan_desc.setStyleSheet(
            f"color: {subtext}; background: transparent; border: none;"
        )

        _cb_check_img = "assets/check_white.png" if is_dark else "assets/check_blue.png"
        _cb_border = "#ffffff" if is_dark else "#c8c8c8"
        _cb_style = f"""
            QCheckBox {{ font-size: 11px; color: {subtext}; background: transparent; padding: 0 4px; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {_cb_border};
                border-radius: 3px;
                background: transparent;
            }}
            QCheckBox::indicator:checked {{
                border: 1px solid #0078d4;
                image: url({_cb_check_img});
            }}
            QCheckBox::indicator:hover {{ border-color: #0078d4; }}
        """
        self.search_shared_cb.setStyleSheet(_cb_style)
        self.case_sensitive_cb.setStyleSheet(_cb_style)

        # Scan page specific themes
        banner_bg = "#1f2937" if is_dark else "#eff6fc"  # Dark slate blue
        banner_border = "#374151" if is_dark else "#cce4f7"
        self.scan_banner.setStyleSheet(
            f"QWidget {{ background-color: {banner_bg}; border: 1px solid {banner_border}; border-radius: 6px; }} QLabel {{ border: none; background: transparent; color: {fg}; }}"
        )
        if hasattr(self, "scan_banner_text"):
            self.scan_banner_text.setStyleSheet(
                f"font-size: 13px; color: {fg}; background: transparent; border: none;"
            )

        self.scan_action_card.setStyleSheet(
            f"QFrame {{ background: {card}; border: 1px solid {border}; border-radius: 8px; }} QLabel {{ border: none; background: transparent; color: {fg}; }}"
        )
        if hasattr(self, "scan_card_title"):
            self.scan_card_title.setStyleSheet(
                f"font-size: 14px; font-weight: 600; color: {fg}; background: transparent; border: none;"
            )
        if hasattr(self, "scan_card_desc"):
            self.scan_card_desc.setStyleSheet(
                f"font-size: 12px; color: {subtext}; background: transparent; border: none;"
            )

        # Individual scan cards dynamically created
        card_bg = "#2d2d2d" if is_dark else "#fafafa"
        border = "#444444" if is_dark else "#e5e5e5"
        text_color = "#ffffff" if is_dark else "#1a1a1a"
        btn_bg = "#444444" if is_dark else "#f0f0f0"
        btn_hover = "#555555" if is_dark else "#e0e0e0"
        btn_border = "#555555" if is_dark else "#cccccc"

        if hasattr(self, "scan_dirs_container"):
            # Also update the title label if it exists
            for child in self.scan_dirs_layout.parent().children():
                if isinstance(child, QLabel):
                    child.setStyleSheet(
                        f"color: {text_color}; background: transparent;"
                    )
                    break

            for frame in self.scan_dirs_container.findChildren(QFrame):
                if frame.objectName() == "IndividualScanCard":
                    frame.setStyleSheet(
                        f"QFrame {{ background: {card_bg}; border: none; border-radius: 6px; }}"
                    )
                    for child in frame.findChildren(QLabel):
                        if child.objectName() == "ScanCardPath":
                            child.setStyleSheet(
                                f"font-size: 13px; color: {text_color}; border: none; background: transparent; font-weight: 500;"
                            )
                        elif child.objectName() == "ScanCardLast":
                            child.setStyleSheet(
                                f"font-size: 11px; color: {subtext}; border: none; background: transparent;"
                            )
                    for child in frame.findChildren(QPushButton):
                        child.setStyleSheet(
                            f"""
                            QPushButton {{
                                background: {btn_bg}; border: 1px solid {btn_border}; border-radius: 4px;
                                padding: 0 16px; font-weight: 500; color: {text_color};
                            }}
                            QPushButton:hover {{ background: {btn_hover}; }}
                        """
                        )

        # Search bar theme
        self.search_bar.setStyleSheet(
            f"""
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
        """
        )

        # Update checkbox styles in menus for visibility (Task 6 fix)
        _menu_cb_style = f"""
            QCheckBox {{ color: {fg}; padding: 4px 10px; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {_cb_border};
                border-radius: 3px;
                background: transparent;
            }}
            QCheckBox::indicator:checked {{
                border: 1px solid #0078d4;
                image: url({_cb_check_img});
            }}
            QCheckBox::indicator:hover {{ border-color: #0078d4; }}
        """
        for cb in self.location_checkboxes.values():
            cb.setStyleSheet(_menu_cb_style)
        for cb in self.type_checkboxes.values():
            cb.setStyleSheet(_menu_cb_style)

        combo_style = f"""
            QComboBox {{
                background: {card};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px 8px;
                color: {fg};
                font-size: 12px;
            }}
            QComboBox:hover {{
                border: 1px solid #0078d4;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background: {card};
                border: 1px solid {border};
                color: {fg};
                selection-background-color: {'#3d3d3d' if is_dark else '#f0f0f0'};
            }}
        """
        self.date_filter.setStyleSheet(combo_style)

        self.location_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {card};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px 8px;
                color: {fg};
                font-size: 12px;
                text-align: left;
            }}
            QPushButton::menu-indicator {{ image: none; }}
            QPushButton:hover {{ border: 1px solid #0078d4; }}
        """
        )

        self.location_menu.setStyleSheet(
            f"""
            QMenu {{
                background-color: {card};
                border: 1px solid {border};
                color: {fg};
            }}
            QMenu::item {{ padding: 4px 10px; }}
            QMenu::item:selected {{ background-color: {'#3d3d3d' if is_dark else '#f0f0f0'}; }}
        """
        )

        # Style for the Type menu button
        self.type_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {card};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px 8px;
                color: {fg};
                font-size: 12px;
                text-align: left;
            }}
            QPushButton::menu-indicator {{ image: none; }}
            QPushButton:hover {{ border: 1px solid #0078d4; }}
        """
        )

        # Style for Clear All button
        self.clear_filters_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px 8px;
                color: {fg};
                font-size: 12px;
            }}
            QPushButton:hover {{ 
                background: {'#3d3d3d' if is_dark else '#f0f0f0'};
                border-color: #0078d4;
            }}
        """
        )

        self.type_menu.setStyleSheet(
            f"""
            QMenu {{
                background-color: {card};
                border: 1px solid {border};
                color: {fg};
            }}
            QMenu::item {{ padding: 4px 10px; }}
            QMenu::item:selected {{ background-color: {'#3d3d3d' if is_dark else '#f0f0f0'}; }}
        """
        )

        # Update labels in filter bar

        # Sidebar text/icons (handled by NavButton but we can force refresh)
        self.app_logo_lbl.setStyleSheet(
            f"color: {fg}; background: transparent; border: none;"
        )
        for btn in self._nav_btns:
            btn.is_dark = is_dark
            btn._apply(btn._active)

        # Propagate theme to sub-widgets
        self.table.set_theme(is_dark)
        self.settings_panel.set_theme(is_dark)

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def changeEvent(self, event):
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

    def closeEvent(self, event):
        self.closed.emit()
        event.accept()
