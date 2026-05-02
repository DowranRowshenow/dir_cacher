from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QFileDialog, QFrame, QSizePolicy, QComboBox
)
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QFont
import qtawesome as qta


def _card(parent=None) -> tuple[QFrame, QVBoxLayout]:
    """Returns a Win11-style card frame and its layout."""
    frame = QFrame(parent)
    frame.setObjectName("settings_card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    return frame, layout


def _card_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("CardHeader")
    lbl.setStyleSheet(
        "font-size: 13px; font-weight: 600;"
        "padding: 14px 16px 10px 16px; background: transparent; border: none;"
    )
    return lbl


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("color: #ebebeb; margin: 0 0;")
    return line


class SettingRow(QWidget):
    """A single setting row with icon, title, description, and a right-side control."""
    def __init__(self, icon_name: str, icon_color: str,
                 title: str, description: str = "",
                 control: QWidget = None,
                 last: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60 if description else 50)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(14)

        if not last:
            self.setStyleSheet("border-bottom: 1px solid #ebebeb;")

        # Icon
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(QSize(20, 20))
        icon_lbl.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(QSize(18, 18)))
        layout.addWidget(icon_lbl, 0, Qt.AlignVCenter)

        # Text block
        text_block = QVBoxLayout()
        text_block.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 400; color: #1a1a1a; border: none;")
        text_block.addWidget(title_lbl)
        if description:
            desc_lbl = QLabel(description)
            desc_lbl.setStyleSheet("font-size: 12px; color: #6e6e6e; border: none;")
            text_block.addWidget(desc_lbl)
        layout.addLayout(text_block, 1)

        # Right-side control
        if control:
            layout.addWidget(control, 0, Qt.AlignVCenter)


class SettingsPanel(QWidget):
    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #ffffff;")
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 36, 40, 40)
        root.setSpacing(24)

        # ── Page header ──────────────────────────────────
        self._header_label = QLabel("Settings")
        self._header_label.setFont(QFont("Segoe UI Variable Display", 22, QFont.Bold))
        self._header_label.setStyleSheet("font-size: 24px; font-weight: 700; color: #1a1a1a;")
        root.addWidget(self._header_label)

        self._subtitle_label = QLabel("Configure index locations, cache storage, and scanning behaviour.")
        self._subtitle_label.setStyleSheet("font-size: 13px; color: #6e6e6e;")
        root.addWidget(self._subtitle_label)

        # ── Cache card ───────────────────────────────────
        self._storage_label = QLabel("Storage")
        self._storage_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #1a1a1a;")
        root.addWidget(self._storage_label)

        cache_card, cache_layout = _card()
        self._shared_storage_header = _card_header("Shared Network Storage (UNC)")
        cache_layout.addWidget(self._shared_storage_header)
        shared_row = QWidget()
        shared_row.setStyleSheet("border-bottom: 1px solid #ebebeb;")
        shared_row.setFixedHeight(56)
        shared_row_layout = QHBoxLayout(shared_row)
        shared_row_layout.setContentsMargins(16, 0, 16, 0)
        shared_row_layout.setSpacing(10)

        s_icon = QLabel()
        s_icon.setFixedSize(20, 20)
        s_icon.setPixmap(qta.icon("fa5s.network-wired", color="#0078d4").pixmap(QSize(16, 16)))
        s_icon.setStyleSheet("border: none;")

        self.shared_cache_edit = QLineEdit()
        self.shared_cache_edit.setPlaceholderText("Shared SQLite cache (e.g. \\\\server\\share\\shared_cache.db)…")
        self.shared_cache_edit.setFixedHeight(30)


        s_browse_btn = QPushButton("Browse…")
        s_browse_btn.setFixedHeight(30)
        s_browse_btn.setFixedWidth(90)
        s_browse_btn.clicked.connect(lambda: self._browse_cache(self.shared_cache_edit))

        shared_row_layout.addWidget(s_icon)
        shared_row_layout.addWidget(self.shared_cache_edit, 1)
        shared_row_layout.addWidget(s_browse_btn)
        cache_layout.addWidget(shared_row)

        # WAL hint row
        wal_hint = QWidget()
        wal_hint.setFixedHeight(40)
        wal_layout = QHBoxLayout(wal_hint)
        wal_layout.setContentsMargins(16, 0, 16, 0)
        wal_layout.setSpacing(8)
        wal_icon = QLabel()
        wal_icon.setPixmap(qta.icon("fa5s.check-circle", color="#107c10").pixmap(QSize(14, 14)))
        wal_icon.setStyleSheet("border: none;")
        wal_lbl = QLabel("WAL mode + NORMAL sync is enabled automatically for best network performance.")
        wal_lbl.setStyleSheet("font-size: 12px; color: #6e6e6e; border: none;")
        wal_layout.addWidget(wal_icon)
        wal_layout.addWidget(wal_lbl, 1)
        cache_layout.addWidget(wal_hint)

        root.addWidget(cache_card)

        # ── Indexing sources card ─────────────────────────
        self._indexing_sources_label = QLabel("Indexing Sources")
        self._indexing_sources_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #1a1a1a;")
        root.addWidget(self._indexing_sources_label)

        sources_card, sources_layout = _card()
        self._directories_to_index_header = _card_header("Directories to Index")
        sources_layout.addWidget(self._directories_to_index_header)

        list_row = QWidget()
        list_row_layout = QVBoxLayout(list_row)
        list_row_layout.setContentsMargins(16, 0, 16, 12)
        list_row_layout.setSpacing(10)

        self.dir_list = QListWidget()
        self.dir_list.setFixedHeight(140)


        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._add_btn = QPushButton("  Add Folder")
        self._add_btn.setFixedHeight(32)
        self._add_btn.setIcon(qta.icon("fa5s.folder-plus", color="white"))
        self._add_btn.setIconSize(QSize(14, 14))
        self._add_btn.clicked.connect(self._add_directory)
        self._add_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4; color: white; border: none;
                border-radius: 4px; font-size: 13px; font-weight: 600;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #0067b8; }
            QPushButton:pressed { background-color: #005a9e; }
        """)

        self._add_manual_btn = QPushButton("  Add UNC Path Manually")
        self._add_manual_btn.setFixedHeight(32)
        self._add_manual_btn.setIcon(qta.icon("fa5s.network-wired", color="white"))
        self._add_manual_btn.setIconSize(QSize(14, 14))
        self._add_manual_btn.clicked.connect(self._add_directory_manual)
        self._add_manual_btn.setStyleSheet("""
            QPushButton {
                background-color: #107c10; color: white; border: none;
                border-radius: 4px; font-size: 13px; font-weight: 600;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #0d620d; }
        """)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setFixedHeight(32)
        self.remove_btn.clicked.connect(self._remove_directory)

        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._add_manual_btn)
        btn_row.addWidget(self.remove_btn)
        btn_row.addStretch()

        list_row_layout.addWidget(self.dir_list)
        list_row_layout.addLayout(btn_row)
        sources_layout.addWidget(list_row)

        root.addWidget(sources_card)

        # ── Appearance Section ──────────────────────────────
        self._appearance_label = QLabel("Appearance")
        self._appearance_label.setFont(QFont("Segoe UI Variable Display", 14, QFont.Bold))
        self._appearance_label.setStyleSheet("color: #1a1a1a; margin-top: 20px; background: transparent; border: none;")
        root.addWidget(self._appearance_label)

        app_card, app_layout = _card()
        
        # Language row
        lang_row = QWidget()
        lang_row.setStyleSheet("border-bottom: 1px solid #ebebeb;")
        lang_row.setFixedHeight(56)
        lang_layout = QHBoxLayout(lang_row)
        lang_layout.setContentsMargins(16, 0, 16, 0)
        
        self._language_label = QLabel("Language")
        self._language_label.setStyleSheet("font-size: 13px; color: #1a1a1a; border: none;")
        self.lang_combo = QComboBox()
        # Mapping for full names
        self.lang_map = {
            "English": "en",
            "Türkçe": "tr",
            "Русский": "ru",
            "Türkmençe": "tk"
        }
        self.lang_combo.addItems(list(self.lang_map.keys()))
        self.lang_combo.setFixedWidth(140)
        self.lang_combo.currentTextChanged.connect(lambda: self.settings_changed.emit())
        
        lang_layout.addWidget(self._language_label)
        lang_layout.addStretch()
        lang_layout.addWidget(self.lang_combo)
        app_layout.addWidget(lang_row)

        # Theme row
        theme_row = QWidget()
        theme_row.setFixedHeight(56)
        theme_layout = QHBoxLayout(theme_row)
        theme_layout.setContentsMargins(16, 0, 16, 0)
        
        self._theme_label = QLabel("Theme")
        self._theme_label.setStyleSheet("font-size: 13px; color: #1a1a1a; border: none;")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["System Default", "Light", "Dark"])
        self.theme_combo.setFixedWidth(140)
        self.theme_combo.currentTextChanged.connect(lambda: self.settings_changed.emit())
        
        theme_layout.addWidget(self._theme_label)
        theme_layout.addStretch()
        theme_layout.addWidget(self.theme_combo)
        app_layout.addWidget(theme_row)
        
        root.addWidget(app_card)
        root.addStretch()

    # ── Actions ───────────────────────────────────────────

    def update_translations(self, t: dict):
        self._header_label.setText(t["settings"])
        if hasattr(self, '_storage_label'): self._storage_label.setText("Storage") 
        if hasattr(self, '_shared_storage_header'): self._shared_storage_header.setText(t["shared_storage"])
        if hasattr(self, '_indexing_sources_label'): self._indexing_sources_label.setText(t["indexing_sources"])
        if hasattr(self, '_directories_to_index_header'): self._directories_to_index_header.setText(t["indexing_sources"]) 
        self._add_btn.setText("  " + t["add_folder"])
        self._add_manual_btn.setText("  " + t["add_unc"])
        self.remove_btn.setText(t["remove"])
        self._appearance_label.setText("Appearance") 
        self._language_label.setText(t["language"])
        self._theme_label.setText(t["theme"])
        
        # Update theme combo box items without triggering signal
        self.theme_combo.blockSignals(True)
        curr_idx = self.theme_combo.currentIndex()
        self.theme_combo.clear()
        self.theme_combo.addItems([t["system"], t["light"], t["dark"]])
        self.theme_combo.setCurrentIndex(curr_idx if curr_idx >= 0 else 0)
        self.theme_combo.blockSignals(False)

    def _browse_cache(self, edit_field: QLineEdit):
        path, _ = QFileDialog.getSaveFileName(
            self, "Select Cache Database", "", "SQLite Database (*.db)"
        )
        if path:
            edit_field.setText(path)
            self.settings_changed.emit()

    def _add_directory(self):
        path = QFileDialog.getExistingDirectory(self, "Select Directory to Index")
        if path:
            self.dir_list.addItem(path)
            self.settings_changed.emit()

    def _add_directory_manual(self):
        from PySide6.QtWidgets import QInputDialog
        path, ok = QInputDialog.getText(self, "Add UNC Path", "Enter network path (e.g. \\\\server\\share):")
        if ok and path:
            self.dir_list.addItem(path.strip())
            self.settings_changed.emit()

    def _remove_directory(self):
        for item in self.dir_list.selectedItems():
            self.dir_list.takeItem(self.dir_list.row(item))
        self.settings_changed.emit()

    def set_theme(self, is_dark: bool):
        bg = "#1e1e1e" if is_dark else "#ffffff"
        fg = "#ffffff" if is_dark else "#1a1a1a"
        border = "#333333" if is_dark else "#ebebeb"
        card = "#2d2d2d" if is_dark else "#fafafa"
        subtext = "#aaaaaa" if is_dark else "#6e6e6e"
        
        # 1. Update main panel background
        self.setStyleSheet(f"background-color: {bg}; color: {fg}; border: none;")
        
        # 2. Update headers
        self._header_label.setStyleSheet(f"font-size: 24px; font-weight: 700; color: {fg}; background: transparent; border: none;")
        self._subtitle_label.setStyleSheet(f"font-size: 13px; color: {subtext}; background: transparent; border: none;")
        
        # 3. Global CSS for dynamic components
        style = f"""
            SettingsPanel {{ background-color: {bg}; }}
            QFrame#settings_card {{ background-color: {card}; border: 1px solid {border}; border-radius: 8px; }}
            QLabel {{ color: {fg}; background: transparent; border: none; }}
            QLabel#CardHeader {{ color: {fg}; font-weight: 600; }}
            QLineEdit {{ background: {card}; color: {fg}; border: 1px solid {border}; border-radius: 4px; padding: 0 10px; font-size: 13px; }}
            QLineEdit:focus {{ border: 1px solid #0078d4; }}
            QComboBox {{ background: {card}; color: {fg}; border: 1px solid {border}; border-radius: 4px; padding: 4px 10px; font-size: 13px; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox::down-arrow {{ image: none; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 5px solid {subtext}; margin-top: 2px; }}
            QComboBox QAbstractItemView {{ background-color: {card}; color: {fg}; selection-background-color: {'#3d3d3d' if is_dark else '#cce4f7'}; border: 1px solid {border}; outline: none; }}
            QListWidget {{ background: {card}; color: {fg}; border: 1px solid {border}; border-radius: 6px; outline: none; }}
            QListWidget::item {{ padding: 8px 12px; border-radius: 4px; }}
            QListWidget::item:selected {{ background-color: {'#3d3d3d' if is_dark else '#cce4f7'}; color: {fg}; }}
            QListWidget::item:hover {{ background-color: {'#333333' if is_dark else '#f0f0f0'}; }}
            QPushButton {{ background: {card}; color: {fg}; border: 1px solid {border}; border-radius: 4px; padding: 4px 12px; }}
            QPushButton:hover {{ background: {'#3d3d3d' if is_dark else '#f5f5f5'}; }}
            
            #SectionLabel {{ color: {fg}; font-weight: bold; margin-top: 10px; }}
        """
        self.setStyleSheet(style)
        
        # Some labels might need direct targeting if they don't inherit
        for lbl in self.findChildren(QLabel):
            if "font-weight: 700" in lbl.styleSheet() or "font-size: 24px" in lbl.styleSheet():
                continue # Header already handled
            lbl.setStyleSheet(f"color: {fg}; background: transparent; border: none;")

        # Update border-bottom for row separators dynamically
        for widget in self.findChildren(QWidget):
            if widget.metaObject().className() == "QWidget":
                if "border-bottom" in widget.styleSheet():
                    widget.setStyleSheet(f"border-bottom: 1px solid {border};")
                    
        if hasattr(self, 'remove_btn'):
            self.remove_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent; color: #c42b1c;
                    border: 1px solid {border}; border-radius: 4px;
                    font-size: 13px; padding: 0 16px;
                }}
                QPushButton:hover {{ background-color: {'rgba(196, 43, 28, 0.2)' if is_dark else 'rgba(196, 43, 28, 0.1)'}; border-color: #c42b1c; }}
            """)
    def get_settings(self) -> dict:
        lang_name = self.lang_combo.currentText()
        lang_code = self.lang_map.get(lang_name, "en")
        return {
            "shared_cache_path": self.shared_cache_edit.text().strip(),
            "scan_dirs": [
                self.dir_list.item(i).text()
                for i in range(self.dir_list.count())
            ],
            "language": lang_code,
            "theme": self.theme_combo.currentText()
        }
