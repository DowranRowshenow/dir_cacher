import os
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QRadioButton,
    QPushButton,
    QFileDialog,
    QButtonGroup,
    QFrame,
    QCheckBox,
    QMenu,
    QWidgetAction,
)
from PySide6.QtCore import Qt


class ExportDialog(QDialog):
    @staticmethod
    def _checkbox_sheet(fg: str, indicator_border: str) -> str:
        blue = (
            Path(__file__).resolve().parents[1] / "assets" / "check_blue.png"
        ).as_posix()
        return f"""
            QCheckBox {{
                font-size: 13px; color: {fg}; background: transparent;
            }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {indicator_border};
                border-radius: 3px;
                background: transparent;
            }}
            QCheckBox::indicator:checked {{
                border: 1px solid #0078d4;
                image: url({blue});
            }}
            QCheckBox::indicator:hover {{ border-color: #0078d4; }}
        """

    def __init__(self, scan_dirs, current_path, is_dark, t, parent=None):
        super().__init__(parent)
        self._t = t
        self.setWindowTitle(t.get("export_wizard", "Export Wizard"))
        self.setMinimumWidth(450)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

        if is_dark:
            from ui.styles import apply_dark_title_bar

            self.show()
            apply_dark_title_bar(self, True)

        bg = "#1e1e1e" if is_dark else "#ffffff"
        fg = "#ffffff" if is_dark else "#1a1a1a"
        input_bg = "#2d2d2d" if is_dark else "#f5f5f5"
        input_border = "#444444" if is_dark else "#e0e0e0"
        btn_bg = "#333333" if is_dark else "#f0f0f0"
        btn_border = "#555555" if is_dark else "#cccccc"
        btn_hover = "#444444" if is_dark else "#e0e0e0"
        sep_color = "#333333" if is_dark else "#e5e5e5"
        cb_border = "#ffffff" if is_dark else "#c8c8c8"

        self._cb_sheet = ExportDialog._checkbox_sheet(fg, cb_border)

        self.setStyleSheet(
            f"""
            QDialog {{ background: {bg}; }}
            QLabel {{ font-size: 13px; color: {fg}; background: transparent; }}
            QRadioButton {{ font-size: 13px; color: {fg}; }}
            QLineEdit, QComboBox {{
                background: {input_bg}; border: 1px solid {input_border};
                border-radius: 4px; padding: 4px 8px; font-size: 13px;
                color: {fg}; min-height: 24px;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid {input_border};
            }}
            QComboBox::down-arrow {{
                image: none;
            }}
            QComboBox QAbstractItemView {{
                background: {input_bg};
                color: {fg};
                selection-background-color: #0078d4;
            }}
            QPushButton {{
                background: {btn_bg}; border: 1px solid {btn_border}; border-radius: 4px;
                padding: 4px 16px; font-weight: 500; color: {fg}; min-height: 24px;
            }}
            QPushButton:hover {{ background: {btn_hover}; }}
            QPushButton#ActionBtn {{
                background: #0078d4; color: #ffffff; border: none;
            }}
            QPushButton#ActionBtn:hover {{ background: #0067b8; }}
        """
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        curr = (current_path or "").strip()

        layout.addWidget(
            QLabel(t.get("export_include_dirs", "Include scan directories:"))
        )

        scope_row = QHBoxLayout()
        self.export_scope_btn = QPushButton()
        self.export_scope_btn.setObjectName("ExportScopeBtn")
        self.export_scope_btn.setMinimumWidth(220)
        self.export_scope_btn.setCursor(Qt.PointingHandCursor)
        self.export_scope_menu = QMenu(self.export_scope_btn)
        self.export_scope_btn.setMenu(self.export_scope_menu)
        self.export_scan_checks = {}

        self.export_scope_menu.setStyleSheet(
            f"""
            QMenu {{
                background: {input_bg};
                border: 1px solid {input_border};
                color: {fg};
                padding: 4px 0;
            }}
            QMenu::item {{ padding: 0; }}
        """
        )

        def _attach_cb(cb):
            cb.setStyleSheet(self._cb_sheet)

            def _changed():
                self._refresh_export_ready()
                self._update_export_scope_btn_text()

            cb.stateChanged.connect(lambda _: _changed())

        for d in sorted(scan_dirs, key=lambda x: x.lower()):
            if not d or not isinstance(d, str):
                continue
            label = os.path.basename(d.rstrip("/\\")) or d
            cb = QCheckBox(label)
            cb.setToolTip(d)
            cb.setChecked(True)
            action = QWidgetAction(self.export_scope_menu)
            action.setDefaultWidget(cb)
            self.export_scope_menu.addAction(action)
            self.export_scan_checks[d] = cb
            _attach_cb(cb)

        self.export_current_cb = None
        self.export_current_path = ""

        added_scan_norms = {
            os.path.normcase(os.path.normpath(os.path.abspath(p)))
            for p in self.export_scan_checks
        }

        curr_n = (
            os.path.normcase(os.path.normpath(os.path.abspath(curr))) if curr else ""
        )
        show_current = curr and curr_n not in added_scan_norms
        if show_current:
            self.export_scope_menu.addSeparator()
            self.export_current_path = curr
            c_label = os.path.basename(curr.rstrip("/\\")) or curr
            if not c_label:
                c_label = curr
            self.export_current_cb = QCheckBox(
                f'{t.get("export_current_folder", "Current folder")}: {c_label}'
            )
            self.export_current_cb.setToolTip(curr)
            self.export_current_cb.setChecked(True)
            ca = QWidgetAction(self.export_scope_menu)
            ca.setDefaultWidget(self.export_current_cb)
            self.export_scope_menu.addAction(ca)
            _attach_cb(self.export_current_cb)

        self.export_scope_btn.setStyleSheet(
            f"""
            QPushButton#ExportScopeBtn {{
                background: {input_bg};
                border: 1px solid {input_border};
                border-radius: 4px;
                padding: 4px 10px;
                color: {fg};
                font-size: 13px;
                text-align: left;
                min-height: 30px;
            }}
            QPushButton#ExportScopeBtn:hover {{
                border: 1px solid #0078d4;
            }}
            QPushButton#ExportScopeBtn::menu-indicator {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
            }}
        """
        )

        scope_row.addWidget(self.export_scope_btn, 1)
        layout.addLayout(scope_row)

        self._update_export_scope_btn_text()

        # Query
        layout.addWidget(QLabel(t.get("search_query_opt", "Search Query (optional):")))
        self.query_edit = QLineEdit()
        layout.addWidget(self.query_edit)

        # Format
        layout.addWidget(QLabel(t.get("export_format", "Export Format:")))
        fmt_layout = QHBoxLayout()
        self.btn_group = QButtonGroup(self)

        self.radio_csv = QRadioButton("CSV (.csv)")
        self.radio_csv.setChecked(True)
        self.btn_group.addButton(self.radio_csv)
        fmt_layout.addWidget(self.radio_csv)

        self.radio_excel = QRadioButton("Excel (.xlsx)")
        self.btn_group.addButton(self.radio_excel)
        fmt_layout.addWidget(self.radio_excel)

        self.radio_txt = QRadioButton("Text (.txt)")
        self.btn_group.addButton(self.radio_txt)
        fmt_layout.addWidget(self.radio_txt)

        fmt_layout.addSpacing(10)
        self.delim_label = QLabel(t.get("delimiter", "Delimiter:"))
        fmt_layout.addWidget(self.delim_label)
        self.delim_combo = QComboBox()
        self.delim_combo.setEditable(True)
        self.delim_combo.addItems(
            [", (Comma)", "\\t (Tab)", "; (Semicolon)", "| (Pipe)"]
        )
        fmt_layout.addWidget(self.delim_combo)

        fmt_layout.addStretch()
        layout.addLayout(fmt_layout)

        def _on_fmt_change():
            is_text = self.radio_csv.isChecked() or self.radio_txt.isChecked()
            self.delim_label.setVisible(is_text)
            self.delim_combo.setVisible(is_text)

        self.radio_csv.toggled.connect(_on_fmt_change)
        self.radio_excel.toggled.connect(_on_fmt_change)
        self.radio_txt.toggled.connect(_on_fmt_change)
        _on_fmt_change()

        # Destination file
        layout.addWidget(QLabel(t.get("dest_file", "Destination File:")))
        dest_layout = QHBoxLayout()
        self.dest_edit = QLineEdit()
        self.dest_edit.setReadOnly(True)
        dest_layout.addWidget(self.dest_edit)

        browse_btn = QPushButton(t.get("browse", "Browse..."))
        browse_btn.clicked.connect(self._browse)
        dest_layout.addWidget(browse_btn)
        layout.addLayout(dest_layout)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {sep_color};")
        layout.addWidget(sep)

        # Actions
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton(t.get("cancel", "Cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.export_btn = QPushButton(t.get("export_btn_txt", "Export"))
        self.export_btn.setObjectName("ActionBtn")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._on_try_export)
        btn_layout.addWidget(self.export_btn)

        layout.addLayout(btn_layout)

        self._refresh_export_ready()

    def _selected_count_and_total(self) -> tuple[int, int]:
        n_checked = sum(
            1 for cb in self.export_scan_checks.values() if cb.isChecked()
        )
        total = len(self.export_scan_checks)
        if self.export_current_cb is not None:
            total += 1
            if self.export_current_cb.isChecked():
                n_checked += 1
        return n_checked, total

    def _update_export_scope_btn_text(self):
        t = getattr(self, "_t", {})
        n, total = self._selected_count_and_total()
        if total == 0:
            self.export_scope_btn.setText(
                t.get("export_scope_setup", "Add scan directories in Settings")
            )
        elif n == 0:
            self.export_scope_btn.setText(t.get("export_scope_none", "No locations"))
        elif n == total:
            self.export_scope_btn.setText(
                t.get("export_scope_all", "All scan directories")
            )
        elif n == 1:
            picked = self.selected_directories()
            d0 = picked[0] if picked else ""
            short = (
                os.path.basename(d0.rstrip("/\\")) or d0
                if d0
                else t.get("export_scope_one", "1 location")
            )
            self.export_scope_btn.setText(short)
        else:
            tpl = t.get("export_scope_count", "{count} locations")
            self.export_scope_btn.setText(tpl.format(count=n))

    def _on_try_export(self):
        if self.selected_directories() and self.dest_edit.text().strip():
            self.accept()

    def _refresh_export_ready(self):
        has_sel = False
        if self.export_current_cb and self.export_current_cb.isChecked():
            has_sel = True
        if not has_sel:
            has_sel = any(cb.isChecked() for cb in self.export_scan_checks.values())
        has_dest = bool(self.dest_edit.text().strip())
        self.export_btn.setEnabled(has_sel and has_dest)

    def selected_directories(self) -> list[str]:
        dirs: list[str] = []
        if self.export_current_cb and self.export_current_cb.isChecked():
            dirs.append(self.export_current_path)
        for path, cb in sorted(
            self.export_scan_checks.items(), key=lambda kv: kv[0].lower()
        ):
            if cb.isChecked():
                dirs.append(path)
        return dirs

    def _browse(self):
        if self.radio_excel.isChecked():
            ext = ".xlsx"
            filter_str = "Excel Files (*.xlsx)"
        elif self.radio_txt.isChecked():
            ext = ".txt"
            filter_str = "Text Files (*.txt)"
        else:
            ext = ".csv"
            filter_str = "CSV Files (*.csv)"

        path, _ = QFileDialog.getSaveFileName(self, "Save Export File", "", filter_str)
        if path:
            if not path.endswith(ext):
                path += ext
            self.dest_edit.setText(path)
        self._refresh_export_ready()

    def get_export_params(self):
        fmt = "xlsx"
        if self.radio_csv.isChecked():
            fmt = "csv"
        elif self.radio_txt.isChecked():
            fmt = "txt"

        delim_text = self.delim_combo.currentText()
        if delim_text.startswith(","):
            delim = ","
        elif delim_text.startswith("\\t"):
            delim = "\t"
        elif delim_text.startswith(";"):
            delim = ";"
        elif delim_text.startswith("|"):
            delim = "|"
        else:
            delim = delim_text

        return {
            "directories": self.selected_directories(),
            "query": self.query_edit.text(),
            "format": fmt,
            "delimiter": delim,
            "destination": self.dest_edit.text(),
        }
