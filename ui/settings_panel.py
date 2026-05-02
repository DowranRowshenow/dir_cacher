from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QFileDialog, QFrame, QSizePolicy
)
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QFont
import qtawesome as qta


def _card(parent=None) -> tuple[QFrame, QVBoxLayout]:
    """Returns a Win11-style card frame and its layout."""
    frame = QFrame(parent)
    frame.setObjectName("settings_card")
    frame.setStyleSheet("""
        QFrame#settings_card {
            background-color: #fafafa;
            border: 1px solid #e5e5e5;
            border-radius: 8px;
        }
    """)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    return frame, layout


def _card_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "font-size: 13px; font-weight: 600; color: #1a1a1a;"
        "padding: 14px 16px 10px 16px;"
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
        header = QLabel("Settings")
        header.setFont(QFont("Segoe UI Variable Display", 22, QFont.Bold))
        header.setStyleSheet("font-size: 24px; font-weight: 700; color: #1a1a1a;")
        root.addWidget(header)

        subtitle = QLabel("Configure index locations, cache storage, and scanning behaviour.")
        subtitle.setStyleSheet("font-size: 13px; color: #6e6e6e;")
        root.addWidget(subtitle)

        # ── Cache card ───────────────────────────────────
        cache_section_lbl = QLabel("Storage")
        cache_section_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #1a1a1a;")
        root.addWidget(cache_section_lbl)

        cache_card, cache_layout = _card()
        cache_layout.addWidget(_card_header("Shared Network Storage (UNC)"))
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
        self.shared_cache_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #c8c8c8; border-radius: 4px;
                background: #ffffff; font-size: 13px; padding: 0 10px;
            }
            QLineEdit:focus { border-color: #0078d4; }
        """)

        s_browse_btn = QPushButton("Browse…")
        s_browse_btn.setFixedHeight(30)
        s_browse_btn.setFixedWidth(90)
        s_browse_btn.setStyleSheet("""
            QPushButton {
                background: #ffffff; border: 1px solid #c8c8c8;
                border-radius: 4px; font-size: 13px; color: #1a1a1a;
            }
            QPushButton:hover { background: #f5f5f5; }
        """)
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
        sources_section_lbl = QLabel("Indexing Sources")
        sources_section_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #1a1a1a;")
        root.addWidget(sources_section_lbl)

        sources_card, sources_layout = _card()
        sources_layout.addWidget(_card_header("Directories to Index"))

        list_row = QWidget()
        list_row_layout = QVBoxLayout(list_row)
        list_row_layout.setContentsMargins(16, 0, 16, 12)
        list_row_layout.setSpacing(10)

        self.dir_list = QListWidget()
        self.dir_list.setFixedHeight(140)
        self.dir_list.setStyleSheet("""
            QListWidget {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                font-size: 13px;
                outline: none;
            }
            QListWidget::item { padding: 8px 12px; border-radius: 4px; }
            QListWidget::item:selected { background-color: #cce4f7; color: #1a1a1a; }
            QListWidget::item:hover { background-color: #f0f0f0; }
        """)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        add_btn = QPushButton("  Add Folder")
        add_btn.setFixedHeight(32)
        add_btn.setIcon(qta.icon("fa5s.folder-plus", color="white"))
        add_btn.setIconSize(QSize(14, 14))
        add_btn.clicked.connect(self._add_directory)
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4; color: white; border: none;
                border-radius: 4px; font-size: 13px; font-weight: 600;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #0067b8; }
            QPushButton:pressed { background-color: #005a9e; }
        """)

        add_manual_btn = QPushButton("  Add UNC Path Manually")
        add_manual_btn.setFixedHeight(32)
        add_manual_btn.setIcon(qta.icon("fa5s.network-wired", color="white"))
        add_manual_btn.setIconSize(QSize(14, 14))
        add_manual_btn.clicked.connect(self._add_directory_manual)
        add_manual_btn.setStyleSheet("""
            QPushButton {
                background-color: #107c10; color: white; border: none;
                border-radius: 4px; font-size: 13px; font-weight: 600;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #0d620d; }
        """)

        remove_btn = QPushButton("Remove")
        remove_btn.setFixedHeight(32)
        remove_btn.clicked.connect(self._remove_directory)
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff; color: #c42b1c;
                border: 1px solid #c8c8c8; border-radius: 4px;
                font-size: 13px; padding: 0 16px;
            }
            QPushButton:hover { background-color: #fff0ee; border-color: #c42b1c; }
        """)

        btn_row.addWidget(add_btn)
        btn_row.addWidget(add_manual_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()

        list_row_layout.addWidget(self.dir_list)
        list_row_layout.addLayout(btn_row)
        sources_layout.addWidget(list_row)

        root.addWidget(sources_card)
        root.addStretch()

    # ── Actions ───────────────────────────────────────────

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

    def get_settings(self) -> dict:
        return {
            "shared_cache_path": self.shared_cache_edit.text().strip(),
            "scan_dirs": [
                self.dir_list.item(i).text()
                for i in range(self.dir_list.count())
            ]
        }
