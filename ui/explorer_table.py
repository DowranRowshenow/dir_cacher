import os
import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMenu, QApplication, QFrame
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor, QFont, QCursor
import qtawesome as qta

# ── Extension → icon map ──────────────────────────────────
EXT_ICONS = {
    ".pdf":  ("fa5s.file-pdf",        "#e74c3c"),
    ".doc":  ("fa5s.file-word",       "#2b5797"),
    ".docx": ("fa5s.file-word",       "#2b5797"),
    ".xls":  ("fa5s.file-excel",      "#1d6f42"),
    ".xlsx": ("fa5s.file-excel",      "#1d6f42"),
    ".xlsm": ("fa5s.file-excel",      "#1d6f42"),
    ".ppt":  ("fa5s.file-powerpoint", "#c43e1c"),
    ".pptx": ("fa5s.file-powerpoint", "#c43e1c"),
    ".txt":  ("fa5s.file-alt",        "#6e6e6e"),
    ".csv":  ("fa5s.file-csv",        "#1d6f42"),
    ".zip":  ("fa5s.file-archive",    "#f0a30a"),
    ".rar":  ("fa5s.file-archive",    "#f0a30a"),
    ".7z":   ("fa5s.file-archive",    "#f0a30a"),
    ".png":  ("fa5s.file-image",      "#8764b8"),
    ".jpg":  ("fa5s.file-image",      "#8764b8"),
    ".jpeg": ("fa5s.file-image",      "#8764b8"),
    ".gif":  ("fa5s.file-image",      "#8764b8"),
    ".svg":  ("fa5s.file-image",      "#8764b8"),
    ".py":   ("fa5s.file-code",       "#3572A5"),
    ".js":   ("fa5s.file-code",       "#f7df1e"),
    ".ts":   ("fa5s.file-code",       "#3178c6"),
    ".html": ("fa5s.file-code",       "#e34c26"),
    ".css":  ("fa5s.file-code",       "#264de4"),
    ".rs":   ("fa5s.file-code",       "#dea584"),
    ".json": ("fa5s.file-code",       "#cbcb41"),
    ".exe":  ("fa5s.cog",             "#6e6e6e"),
    ".lnk":  ("fa5s.external-link-alt","#868686"),
    ".mp4":  ("fa5s.file-video",      "#c43e1c"),
    ".mp3":  ("fa5s.file-audio",      "#1db954"),
}
_ICON_CACHE: dict = {}

def _icon(name: str, color: str, sz: int = 16):
    key = (name, color, sz)
    if key not in _ICON_CACHE:
        _ICON_CACHE[key] = qta.icon(name, color=color).pixmap(QSize(sz, sz))
    return _ICON_CACHE[key]


# ── Breadcrumb bar ────────────────────────────────────────
class BreadcrumbBar(QWidget):
    navigate_to = Signal(str)   # emits a full path when a crumb is clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet("background: transparent;")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._path = ""

    def set_path(self, path: str, root_label: str = ""):
        self._path = path
        # Clear old crumbs
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Build breadcrumb parts
        parts = []
        if root_label:
            parts.append((root_label, None))   # virtual root — no navigation

        # Split actual path into parts relative to display
        norm = path.replace("\\", "/")
        segments = norm.rstrip("/").split("/")
        accumulated = ""
        for i, seg in enumerate(segments):
            if not seg:
                accumulated = "/"
                continue
            accumulated = accumulated.rstrip("/") + "/" + seg if accumulated else seg
            parts.append((seg, accumulated.replace("/", os.sep)))

        for i, (label, nav_path) in enumerate(parts):
            if i > 0:
                sep = QLabel("›")
                sep.setStyleSheet("color: #aaaaaa; font-size: 14px; padding: 0 4px;")
                self._layout.addWidget(sep)

            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            is_last = (i == len(parts) - 1)
            btn.setStyleSheet(f"""
                QPushButton {{
                    color: {'#1a1a1a' if is_last else '#0078d4'};
                    font-size: 13px;
                    font-weight: {'600' if is_last else '400'};
                    border: none;
                    background: transparent;
                    padding: 0 2px;
                }}
                QPushButton:hover {{
                    color: #0067b8;
                    text-decoration: underline;
                }}
            """)
            if nav_path and not is_last:
                btn.clicked.connect(lambda _, p=nav_path: self.navigate_to.emit(p))
            self._layout.addWidget(btn)

        self._layout.addStretch()


# ── Explorer Table ────────────────────────────────────────
class ExplorerTable(QWidget):
    folder_opened    = Signal(str)   # path of folder double-clicked
    status_updated   = Signal(str, str)  # status text, count text

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Toolbar: back button + breadcrumb
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._back_btn = QPushButton()
        self._back_btn.setIcon(qta.icon("fa5s.arrow-left", color="#1a1a1a"))
        self._back_btn.setIconSize(QSize(14, 14))
        self._back_btn.setFixedSize(28, 28)
        self._back_btn.setEnabled(False)
        self._back_btn.setToolTip("Go back")
        self._back_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: 1px solid transparent;
                border-radius: 4px;
            }
            QPushButton:hover:enabled { background: #f0f0f0; border-color: #d1d1d1; }
            QPushButton:disabled { opacity: 0.3; }
        """)
        self._back_btn.clicked.connect(self._go_back)

        self._breadcrumb = BreadcrumbBar()
        self._breadcrumb.navigate_to.connect(self._on_breadcrumb_nav)

        toolbar.addWidget(self._back_btn)
        toolbar.addWidget(self._breadcrumb, 1)
        layout.addLayout(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Name", "Type", "Size", "Date Modified"])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.Fixed)
        hh.resizeSection(1, 76)
        hh.resizeSection(2, 86)
        hh.resizeSection(3, 160)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setIconSize(QSize(16, 16))
        self._table.verticalHeader().setDefaultSectionSize(32)
        self._table.setStyleSheet("""
            QTableWidget::item { padding-left: 6px; }
        """)
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self._table)

        # Navigation state
        self._history: list[str] = []
        self._current_path: str = ""
        self._root_label: str = ""
        self._get_children_fn = None  # injected by main

    # ── Public API ─────────────────────────────────────────
    def set_data_source(self, get_children_fn):
        """Inject the DB lookup function."""
        self._get_children_fn = get_children_fn

    def navigate_to(self, path: str, root_label: str = "", push_history: bool = True):
        if not self._get_children_fn:
            return
        if push_history and self._current_path:
            self._history.append(self._current_path)
        self._current_path = path
        self._root_label = root_label or self._root_label
        self._back_btn.setEnabled(bool(self._history))
        items = self._get_children_fn(path)
        self._load_items(items)
        self._breadcrumb.set_path(path, self._root_label)
        n = len(items)
        self.status_updated.emit(
            f"{'1 item' if n == 1 else f'{n:,} items'} in this folder.",
            f"{n:,} items"
        )

    def show_virtual_roots(self, roots: list[dict], label: str = ""):
        """Show a list of virtual root entries (multiple scan dirs)."""
        self._history.clear()
        self._current_path = ""
        self._root_label = label
        self._back_btn.setEnabled(False)
        self._load_items(roots)
        self._breadcrumb.set_path("", "")
        n = len(roots)
        self.status_updated.emit(f"{n} root{'s' if n != 1 else ''} configured.", f"{n} roots")

    def set_search_results(self, items: list[dict], query: str):
        self._load_items(items)
        n = len(items)
        self._breadcrumb.set_path("", f'Search: "{query}"')
        self.status_updated.emit(
            f"{n:,} result{'s' if n != 1 else ''} for \"{query}\".",
            f"{n:,} results"
        )

    # ── Navigation ─────────────────────────────────────────
    def _go_back(self):
        if self._history:
            prev = self._history.pop()
            self.navigate_to(prev, push_history=False)

    def _on_breadcrumb_nav(self, path: str):
        self.navigate_to(path)

    def _on_double_click(self, index):
        row = index.row()
        item = self._table.item(row, 0)
        if not item:
            return
        data = item.data(Qt.UserRole)
        if data and data.get("is_dir"):
            path = data["path"]
            self._history.append(self._current_path)
            self.navigate_to(path, push_history=False)

    # ── Rendering ──────────────────────────────────────────
    def _load_items(self, items: list[dict]):
        tbl = self._table
        tbl.setUpdatesEnabled(False)
        tbl.blockSignals(True)
        tbl.setRowCount(0)

        for item in items:
            row = tbl.rowCount()
            tbl.insertRow(row)
            is_dir = item.get("is_dir", False)
            name   = item.get("name", "")
            path   = item.get("path", "")
            ext    = os.path.splitext(name)[1].lower()

            # Col 0 — Name + icon
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.UserRole, {"path": path, "is_dir": is_dir})
            if is_dir:
                name_item.setIcon(qta.icon("fa5s.folder", color="#f0a30a"))
                name_item.setFont(QFont("Segoe UI Variable Text", 10))
            else:
                icon_name, color = EXT_ICONS.get(ext, ("fa5s.file", "#868686"))
                name_item.setIcon(qta.icon(icon_name, color=color))
            tbl.setItem(row, 0, name_item)

            # Col 1 — Type
            type_str = "Folder" if is_dir else (ext.upper().lstrip(".") or "File")
            t = QTableWidgetItem(type_str)
            t.setForeground(QColor("#888888"))
            tbl.setItem(row, 1, t)

            # Col 2 — Size
            size_val  = item.get("size", 0)
            size_str  = "" if is_dir else self._fmt_size(size_val)
            s = QTableWidgetItem(size_str)
            s.setForeground(QColor("#888888"))
            s.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tbl.setItem(row, 2, s)

            # Col 3 — Date
            mtime = item.get("mtime", 0)
            try:
                dt = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d  %H:%M")
            except Exception:
                dt = ""
            d = QTableWidgetItem(dt)
            d.setForeground(QColor("#888888"))
            tbl.setItem(row, 3, d)

        tbl.blockSignals(False)
        tbl.setUpdatesEnabled(True)

    # ── Context menu ───────────────────────────────────────
    def _context_menu(self, pos):
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        item = self._table.item(row, 0)
        if not item:
            return
        data = item.data(Qt.UserRole) or {}
        path = data.get("path", "")

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #ffffff; border: 1px solid #d1d1d1;
                border-radius: 8px; padding: 4px; font-size: 13px;
            }
            QMenu::item { padding: 7px 20px; border-radius: 4px; }
            QMenu::item:selected { background: #f0f7ff; }
            QMenu::separator { background: #e5e5e5; height: 1px; margin: 3px 8px; }
        """)
        open_act   = menu.addAction(qta.icon("fa5s.external-link-alt", color="#1a1a1a"), "Open")
        reveal_act = menu.addAction(qta.icon("fa5s.folder-open",       color="#f0a30a"), "Show in File Explorer")
        menu.addSeparator()
        copy_act   = menu.addAction(qta.icon("fa5s.copy",  color="#888888"), "Copy Path")

        action = menu.exec(QCursor.pos())
        if not path:
            return
        if action == copy_act:
            QApplication.clipboard().setText(path)
        elif action == open_act:
            try:
                os.startfile(path)
            except Exception:
                pass
        elif action == reveal_act:
            target = path if os.path.isdir(path) else os.path.dirname(path)
            try:
                os.startfile(target)
            except Exception:
                pass

    @staticmethod
    def _fmt_size(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
