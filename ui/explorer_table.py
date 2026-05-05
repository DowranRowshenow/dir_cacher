import os
import datetime
import ctypes
from ctypes import wintypes
import html
import re
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QMenu,
    QApplication,
    QFrame,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
)
from PySide6.QtCore import Qt, QSize, Signal, QEvent
from PySide6.QtGui import (
    QColor,
    QFont,
    QCursor,
    QTextDocument,
    QAbstractTextDocumentLayout,
)
import qtawesome as qta
from ui.icon_provider import IconProvider

# (EXT_ICONS removed, replaced by dynamic IconProvider)
_ICON_CACHE: dict = {}


def _icon(name: str, color: str, sz: int = 16):
    key = (name, color, sz)
    if key not in _ICON_CACHE:
        _ICON_CACHE[key] = qta.icon(name, color=color).pixmap(QSize(sz, sz))
    return _ICON_CACHE[key]


# ── Search Highlight Delegate ─────────────────────────────
class HighlightDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query = ""

    def set_query(self, query: str):
        self.query = query.lower()

    def paint(self, painter, option, index):
        if not self.query or index.column() != 0:
            super().paint(painter, option, index)
            return

        text = index.data(Qt.DisplayRole)
        if not text:
            super().paint(painter, option, index)
            return

        idx = text.lower().find(self.query)
        if idx == -1:
            super().paint(painter, option, index)
            return

        # Prepare base style (background, icon, selection state)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # Clear text so drawControl only paints icon/bg
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        # Build rich text HTML
        start = html.escape(text[:idx])
        match = html.escape(text[idx : idx + len(self.query)])
        end = html.escape(text[idx + len(self.query) :])

        html_str = f"<div style='white-space:nowrap;'>{start}<span style='background-color: #ffe8a1; color: #000000;'>{match}</span>{end}</div>"

        doc = QTextDocument()
        doc.setDefaultFont(opt.font)
        doc.setHtml(html_str)

        # Find text bounding rect
        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, opt.widget)

        painter.save()
        painter.translate(text_rect.topLeft())
        painter.setClipRect(text_rect.translated(-text_rect.topLeft()))

        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette = opt.palette

        # Center vertically
        y_offset = (text_rect.height() - doc.size().height()) / 2
        painter.translate(0, max(0, y_offset))

        doc.documentLayout().draw(painter, ctx)
        painter.restore()


# ── Natural Sorting helper ────────────────────────────────
def natural_sort_key(s: str):
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split("([0-9]+)", s)
    ]


# ── Numeric Sorting Table Item ────────────────────────────
class SortableItem(QTableWidgetItem):
    def __init__(self, text: str, is_dir: bool, sort_value=None):
        super().__init__(text)
        self.is_dir = is_dir
        self.sort_value = sort_value if sort_value is not None else text

    def __lt__(self, other):
        if not isinstance(other, SortableItem):
            return super().__lt__(other)

        # Folders always group together at the top (ascending) or bottom (descending)
        # But we want them together.
        if self.is_dir != other.is_dir:
            # If we return self.is_dir, then dir (True) < file (False) is False.
            # So file < dir? No, True is 1, False is 0. 0 < 1.
            # So file < dir.
            # We want dir < file. So return other.is_dir?
            # If self is dir (True) and other is file (False), return True.
            return self.is_dir > other.is_dir

        # Same type: use natural sort for strings, direct compare for others
        s_val = self.sort_value
        o_val = other.sort_value

        if isinstance(s_val, str) and isinstance(o_val, str):
            return natural_sort_key(s_val) < natural_sort_key(o_val)

        # Handle cases where sort_value might be None or different types
        try:
            return s_val < o_val
        except TypeError:
            return str(s_val) < str(o_val)


# ── Breadcrumb bar ────────────────────────────────────────
class BreadcrumbBar(QWidget):
    navigate_to = Signal(str)
    home_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet("background: transparent;")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._path = ""
        self.is_dark = False

    def set_theme(self, is_dark: bool):
        self.is_dark = is_dark

    def set_path(self, path: str, root_label: str = "", root_path: str = ""):
        self._path = path
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add Home icon button
        home_btn = QPushButton()
        home_btn.setIcon(qta.icon("fa5s.home", color="#0078d4"))
        home_btn.setIconSize(QSize(14, 14))
        home_btn.setFixedSize(24, 24)
        home_btn.setFlat(True)
        home_btn.setCursor(Qt.PointingHandCursor)
        home_btn.clicked.connect(self.home_clicked.emit)
        home_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; padding: 0; } QPushButton:hover { background: #f0f0f0; border-radius: 4px; }"
        )
        self._layout.addWidget(home_btn)

        if root_label or path:
            sep = QLabel("›")
            sep.setStyleSheet("color: #aaaaaa; font-size: 14px; padding: 0 4px;")
            self._layout.addWidget(sep)

        parts = []
        if root_label:
            parts.append((root_label, root_path))

        # Normalize slashes for comparison
        p = path.replace("\\", "/")
        r = root_path.replace("\\", "/")

        # Ensure we don't have trailing slashes interfering
        norm_path = p.rstrip("/")
        norm_root = r.rstrip("/")

        rel_path = norm_path
        if norm_root:
            if norm_path == norm_root:
                rel_path = ""
            elif norm_path.startswith(norm_root + "/"):
                rel_path = norm_path[len(norm_root) :]

        norm = rel_path.strip("/")
        if norm:
            segments = norm.split("/")
            current_path = path
            path_segments = []
            for seg in reversed(segments):
                path_segments.append((seg, current_path))
                # Find the segment at the end and slice it off
                idx = current_path.rfind(seg)
                if idx >= 0:
                    current_path = current_path[:idx].rstrip("\\/")

            parts.extend(reversed(path_segments))

        for i, (label, nav_path) in enumerate(parts):
            if i > 0:
                sep = QLabel("›")
                sep.setStyleSheet("color: #aaaaaa; font-size: 14px; padding: 0 4px;")
                self._layout.addWidget(sep)

            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            is_last = i == len(parts) - 1
            fg = "#ffffff" if self.is_dark else "#1a1a1a"
            hover_bg = "rgba(255,255,255,0.1)" if self.is_dark else "#f0f0f0"
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    color: {fg if is_last else '#0078d4'};
                    font-size: 13px;
                    font-weight: {'600' if is_last else '400'};
                    border: none;
                    background: transparent;
                    padding: 0 2px;
                }}
                QPushButton:hover {{
                    background: {hover_bg};
                    border-radius: 4px;
                    color: #0078d4;
                    text-decoration: underline;
                }}
            """
            )
            if nav_path and not is_last:
                btn.clicked.connect(lambda _, p=nav_path: self.navigate_to.emit(p))
            self._layout.addWidget(btn)

        self._layout.addStretch()


# ── Explorer Table ────────────────────────────────────────
class ExplorerTable(QWidget):
    folder_opened = Signal(str)
    status_updated = Signal(str, str)
    home_requested = Signal()
    scan_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._icon_provider = IconProvider()

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._back_btn = QPushButton()
        self._back_btn.setIcon(qta.icon("fa5s.arrow-left", color="#1a1a1a"))
        self._back_btn.setIconSize(QSize(14, 14))
        self._back_btn.setFixedSize(28, 28)
        self._back_btn.setEnabled(False)
        self._back_btn.setToolTip("Go back")
        self._back_btn.setStyleSheet(
            """
            QPushButton {
                background: transparent; border: 1px solid transparent;
                border-radius: 4px;
            }
            QPushButton:hover:enabled { background: #f0f0f0; border-color: #d1d1d1; }
            QPushButton:disabled { opacity: 0.3; }
        """
        )
        self._back_btn.clicked.connect(self._go_back)

        self._breadcrumb = BreadcrumbBar()
        self._breadcrumb.navigate_to.connect(self._on_breadcrumb_nav)
        self._breadcrumb.home_clicked.connect(self.home_requested.emit)

        toolbar.addWidget(self._back_btn)
        toolbar.addWidget(self._breadcrumb, 1)
        layout.addLayout(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self.column_names = ["Name", "Type", "Size", "Date Modified", "Date Created", "Author"]
        self._table.setHorizontalHeaderLabels(self.column_names)
        
        hh = self._table.horizontalHeader()
        hh.setContextMenuPolicy(Qt.CustomContextMenu)
        hh.customContextMenuRequested.connect(self._header_context_menu)
        
        for i in range(6):
            hh.setSectionResizeMode(i, QHeaderView.Interactive)
        
        hh.resizeSection(0, 400)
        hh.resizeSection(1, 100)
        hh.resizeSection(2, 80)
        hh.resizeSection(3, 140)
        hh.resizeSection(4, 140)
        hh.resizeSection(5, 120)
        
        hh.setStretchLastSection(True)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setCascadingSectionResizes(True)
        hh.setSortIndicatorShown(True)
        hh.setSectionsMovable(True)

        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setFocusPolicy(Qt.StrongFocus)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setIconSize(QSize(16, 16))
        self._table.verticalHeader().setDefaultSectionSize(32)
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)

        # Enable Sorting
        self._table.setSortingEnabled(True)

        # Highlight delegate
        self._highlight_delegate = HighlightDelegate(self._table)
        self._table.setItemDelegate(self._highlight_delegate)

        # Install event filter on viewport to catch wheel events before the table handles them
        self._table.viewport().installEventFilter(self)

        layout.addWidget(self._table)

        # Navigation state
        self._history: list[str] = []
        self._current_path: str = ""
        self._root_label: str = ""
        self._root_path: str = ""
        self._get_children_fn = None

    def set_theme(self, is_dark: bool):
        bg = "#1e1e1e" if is_dark else "#ffffff"
        fg = "#ffffff" if is_dark else "#1a1a1a"
        border = "#333333" if is_dark else "#ebebeb"
        header = "#252525" if is_dark else "#f9f9f9"

        self._highlight_delegate.is_dark = is_dark
        self.setStyleSheet(f"background: {bg}; border: none;")

        # We need to add set_theme to Breadcrumb if not present
        if hasattr(self._breadcrumb, "set_theme"):
            self._breadcrumb.set_theme(is_dark)

        self._back_btn.setIcon(qta.icon("fa5s.arrow-left", color=fg))

        self._table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {bg};
                alternate-background-color: {'#252525' if is_dark else '#f9f9f9'};
                color: {fg};
                gridline-color: {border};
                border: none;
                selection-background-color: {'#3d3d3d' if is_dark else '#e5f3ff'};
            }}
            QHeaderView::section {{
                background-color: {header};
                color: {fg};
                border: none;
                border-bottom: 1px solid {border};
                border-right: 1px solid {border};
                padding: 4px;
                padding-left: 6px;
                font-weight: 600;
            }}
            QTableWidget::item {{
                border-bottom: 1px solid {border};
                padding-left: 6px;
            }}
            QTableWidget::item:hover {{
                background-color: {'rgba(255,255,255,0.05)' if is_dark else 'rgba(0,0,0,0.03)'};
            }}
            QTableWidget::item:selected {{
                background-color: {'#3d3d3d' if is_dark else '#e5f3ff'};
                color: {fg};
            }}
            QScrollBar:vertical {{
                background: transparent; width: 14px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {'#444444' if is_dark else '#cdcdcd'};
                min-height: 20px; border-radius: 7px; margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {'#555555' if is_dark else '#a6a6a6'};
            }}
            QScrollBar:horizontal {{
                background: transparent; height: 14px; margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: {'#444444' if is_dark else '#cdcdcd'};
                min-width: 20px; border-radius: 7px; margin: 2px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {'#555555' if is_dark else '#a6a6a6'};
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{ border: none; background: none; }}
        """
        )

        self._breadcrumb.set_theme(is_dark)
        self._breadcrumb.set_path(
            self._current_path or "", self._root_label, self._root_path
        )

        # Explicitly style the header to avoid inheriting parent white backgrounds
        header_hover = "#333333" if is_dark else "#f0f0f0"
        self._table.horizontalHeader().setStyleSheet(
            f"""
            QHeaderView::section {{
                background-color: {header};
                color: {fg};
                border: none;
                border-bottom: 1px solid {border};
                border-right: 1px solid {border};
                padding: 4px;
                padding-left: 6px;
                font-weight: 600;
            }}
            QHeaderView::section:hover {{
                background-color: {header_hover};
            }}
        """
        )

    # ── Public API ─────────────────────────────────────────
    def clear_history(self):
        self._history = []
        self._back_btn.setEnabled(False)

    def set_data_source(self, get_children_fn):
        self._get_children_fn = get_children_fn

    def navigate_to(
        self,
        path: str,
        root_label: str = "",
        root_path: str = "",
        push_history: bool = True,
    ):
        if not path:
            self.home_requested.emit()
            return
        if not self._get_children_fn:
            return
        if push_history and self._current_path:
            self._history.append(self._current_path)

        self._current_path = path
        self._root_label = root_label or self._root_label
        self._root_path = root_path or self._root_path

        self._back_btn.setEnabled(len(self._history) > 0)
        items = self._get_children_fn(path)
        self._highlight_delegate.set_query("")
        self._load_items(items)
        self._breadcrumb.set_path(path, self._root_label, self._root_path)

        n = len(items)
        self.status_updated.emit(
            f"{'1 item' if n == 1 else f'{n:,} items'} in this folder.", f"{n:,} items"
        )

    def show_virtual_roots(self, roots: list[dict], label: str = "Indexed Locations"):
        self._history = []
        self._current_path = ""
        self._root_label = label
        self._root_path = ""
        self._back_btn.setEnabled(False)
        self._highlight_delegate.set_query("")
        self._load_items(roots)
        self._breadcrumb.set_path("", label)
        n = len(roots)
        self.status_updated.emit(
            f"{n} root{'s' if n != 1 else ''} configured.", f"{n} roots"
        )

    def set_search_results(self, items: list[dict], query: str):
        self._highlight_delegate.set_query(query)
        self._load_items(items)
        n = len(items)
        self._breadcrumb.set_path("", f'Search: "{query}"')
        self.status_updated.emit(
            f"{n:,} result{'s' if n != 1 else ''} for \"{query}\".", f"{n:,} results"
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

            if not self._current_path:
                # Coming from virtual root
                self.navigate_to(
                    path, root_label=item.text(), root_path=path, push_history=False
                )
            else:
                self.navigate_to(path, push_history=False)

    # ── Rendering ──────────────────────────────────────────
    def _load_items(self, items: list[dict]):
        tbl = self._table
        tbl.setUpdatesEnabled(False)
        tbl.blockSignals(True)
        tbl.setSortingEnabled(False)  # disable during insert
        tbl.setRowCount(0)

        # Folder first sorting
        def sort_key(x):
            return (0 if x.get("is_dir") else 1, x.get("name", "").lower())

        items = sorted(items, key=sort_key)

        for item in items:
            row = tbl.rowCount()
            tbl.insertRow(row)
            is_dir = item.get("is_dir", False)
            name = item.get("name", "")
            path = item.get("path", "")
            ext = os.path.splitext(name)[1].lower()

            # Col 0 — Name (Natural Sort + Folder Priority)
            name_item = SortableItem(name, is_dir)
            name_item.setData(Qt.UserRole, {"path": path, "is_dir": is_dir})

            icon = self._icon_provider.get_icon(path, is_dir)
            name_item.setIcon(icon)

            if is_dir:
                name_item.setFont(QFont("Segoe UI Variable Display", 10))
            tbl.setItem(row, 0, name_item)

            # Col 1 — Type
            type_str = "Folder" if is_dir else (ext.upper().lstrip(".") or "File")
            t = SortableItem(type_str, is_dir)
            t.setForeground(QColor("#888888"))
            tbl.setItem(row, 1, t)

            # Col 2 — Size (Numeric Sortable)
            size_val = item.get("size", 0)
            size_str = self._fmt_size(size_val) if not is_dir else ""
            s = SortableItem(size_str, is_dir, size_val if not is_dir else -1)
            s.setForeground(QColor("#888888"))
            s.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tbl.setItem(row, 2, s)

            # Col 3 — Date Modified (Numeric Sortable)
            mtime = item.get("mtime", 0)
            try:
                dt_m = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d  %H:%M")
            except Exception:
                dt_m = ""
            dm = SortableItem(dt_m, is_dir, mtime)
            dm.setForeground(QColor("#888888"))
            tbl.setItem(row, 3, dm)

            # Col 4 — Date Created (Numeric Sortable)
            ctime = item.get("ctime", 0)
            try:
                dt_c = datetime.datetime.fromtimestamp(ctime).strftime("%Y-%m-%d  %H:%M")
            except Exception:
                dt_c = ""
            dc = SortableItem(dt_c, is_dir, ctime)
            dc.setForeground(QColor("#888888"))
            tbl.setItem(row, 4, dc)

            # Col 5 — Author
            author = item.get("author") or ""
            a = SortableItem(author, is_dir)
            a.setForeground(QColor("#888888"))
            tbl.setItem(row, 5, a)

        tbl.setSortingEnabled(True)
        tbl.blockSignals(False)
        tbl.setUpdatesEnabled(True)

    # ── Context menu ───────────────────────────────────────
    def contextMenuEvent(self, event):
        pos = event.pos()
        item = self._table.itemAt(self._table.viewport().mapFromParent(pos))
        
        # Determine theme-aware colors
        is_dark = self.palette().window().color().lightness() < 128
        
        if item:
            self._context_menu(self._table.viewport().mapFromParent(pos))
        else:
            # Background context menu
            menu = QMenu(self)
            menu.setStyleSheet("QMenu::item { padding: 6px 10px 6px 16px; }")
            
            refresh_act = menu.addAction(qta.icon("fa5s.sync", color="#107c10"), "Refresh Folder")
            
            action = menu.exec(event.globalPos())
            if action == refresh_act and self._current_path:
                self.scan_requested.emit(self._current_path)

    def _header_context_menu(self, pos):
        menu = QMenu(self)
        fg = "#ffffff" if self._highlight_delegate.is_dark else "#1a1a1a"
        bg = "#2d2d2d" if self._highlight_delegate.is_dark else "#ffffff"
        menu.setStyleSheet(f"QMenu {{ background-color: {bg}; color: {fg}; border: 1px solid #555; }} QMenu::item {{ padding: 4px 20px; }} QMenu::item:selected {{ background-color: #0078d4; }}")
        
        for i, name in enumerate(self.column_names):
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(not self._table.isColumnHidden(i))
            # Name column (0) shouldn't be hideable easily, but we allow it
            action.triggered.connect(lambda checked, idx=i: self._table.setColumnHidden(idx, not checked))
        
        menu.exec_(self._table.horizontalHeader().mapToGlobal(pos))

    def wheelEvent(self, event):
        # We handle this via eventFilter on the viewport now
        super().wheelEvent(event)

    def eventFilter(self, source, event):
        if source == self._table.viewport() and event.type() == QEvent.Wheel:
            if event.modifiers() & Qt.ShiftModifier:
                delta = event.angleDelta().y() or event.angleDelta().x()
                self._table.horizontalScrollBar().setValue(
                    self._table.horizontalScrollBar().value() - delta
                )
                return True # Stop propagation
        return super().eventFilter(source, event)

    def _context_menu(self, pos):
        item = self._table.itemAt(pos)
        if not item:
            return
        row = item.row()
        name_item = self._table.item(row, 0)
        if not name_item:
            return
        data = name_item.data(Qt.UserRole) or {}
        path = data.get("path", "")

        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu::item {
                padding: 6px 10px 6px 16px;   /* top right bottom left */
            }
            QMenu::icon {
                margin-left: 6px;
                padding-left: 12px;
                padding-right: 0px;
            }
            """
        )

        # Use theme-aware colors for icons
        is_dark = self.palette().window().color().lightness() < 128
        primary_fg = "#ffffff" if is_dark else "#1a1a1a"
        icon_gray = "#aaaaaa" if is_dark else "#888888"

        open_act = menu.addAction(
            qta.icon("fa5s.external-link-alt", color=primary_fg), "Open"
        )
        reveal_act = menu.addAction(
            qta.icon("fa5s.folder-open", color="#f0a30a"), "Show in File Explorer"
        )
        menu.addSeparator()
        copy_act = menu.addAction(qta.icon("fa5s.copy", color=icon_gray), "Copy Path")
        prop_act = menu.addAction(
            qta.icon("fa5s.info-circle", color=icon_gray), "Properties"
        )
        menu.addSeparator()
        refresh_act = menu.addAction(qta.icon("fa5s.sync", color="#107c10"), "Refresh (Rescan)")


        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        path = self._normalize_path(path)
        if not path:
            return

        if action == copy_act:
            QApplication.clipboard().setText(path)
        elif action == prop_act:
            self._show_native_properties(path)
        elif action == refresh_act:
            if os.path.isdir(path):
                self.scan_requested.emit(path)
            elif self._current_path:
                self.scan_requested.emit(self._current_path)
        elif action == open_act:
            try:
                os.startfile(path)
            except Exception:
                pass
        elif action == reveal_act:
            try:
                import subprocess

                if os.path.isdir(path):
                    os.startfile(path)
                else:
                    subprocess.run(["explorer", "/select,", path])
            except Exception:
                pass

    def _on_context_properties(self):
        """Called via shortcut (Alt+Enter)"""
        items = self._table.selectedItems()
        if not items:
            return
        row = items[0].row()
        name_item = self._table.item(row, 0)
        if not name_item:
            return
        data = name_item.data(Qt.UserRole) or {}
        path = data.get("path", "")
        if path:
            self._show_native_properties(path)

    def _show_native_properties(self, path: str):
        path = self._normalize_path(path)
        if not os.path.exists(path):
            return

        # Windows Shell API to show properties dialog
        SEE_MASK_INVOKEIDLIST = 0x0000000C

        class SHELLEXECUTEINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("fMask", wintypes.ULONG),
                ("hwnd", wintypes.HWND),
                ("lpVerb", wintypes.LPCWSTR),
                ("lpFile", wintypes.LPCWSTR),
                ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR),
                ("nShow", ctypes.c_int),
                ("hInstApp", wintypes.HINSTANCE),
                ("lpIDList", wintypes.LPVOID),
                ("lpClass", wintypes.LPCWSTR),
                ("hkeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD),
                ("hIconOrMonitor", wintypes.HANDLE),
                ("hProcess", wintypes.HANDLE),
            ]

        sei = SHELLEXECUTEINFO()
        sei.cbSize = ctypes.sizeof(sei)
        sei.fMask = SEE_MASK_INVOKEIDLIST
        sei.lpVerb = "properties"
        sei.lpFile = path
        sei.nShow = 5  # SW_SHOW
        ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))

    def _normalize_path(self, path: str) -> str:
        if not path:
            return ""
        # Convert all to backslashes for Windows API
        p = path.replace("/", "\\")
        # Ensure UNC paths start with double backslash
        if path.startswith("//") or path.startswith("\\\\"):
            p = "\\\\" + p.lstrip("\\")
        return os.path.normpath(p)

    @staticmethod
    def _fmt_size(size: int) -> str:
        if size <= 0:
            return ""
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            items = self._table.selectedItems()
            if items:
                row = items[0].row()
                self._on_double_click(self._table.model().index(row, 0))
            event.accept()
        elif event.key() == Qt.Key_Backtab or event.key() == Qt.Key_Backspace:
            if self._back_btn.isEnabled():
                self._go_back()
            event.accept()
        else:
            super().keyPressEvent(event)
