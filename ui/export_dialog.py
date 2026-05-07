import os
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
)
from PySide6.QtCore import Qt


class ExportDialog(QDialog):
    def __init__(self, scan_dirs, current_path, is_dark, t, parent=None):
        super().__init__(parent)
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

        # Title
        # title = QLabel(t.get("export_wizard", "Export Data"))
        # title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {fg};")
        # layout.addWidget(title)

        # Directory selection
        layout.addWidget(QLabel(t.get("target_dir", "Target Directory:")))
        self.dir_combo = QComboBox()
        self.dir_combo.addItem(t.get("all_dirs", "All Configured Directories"), "")
        if current_path:
            self.dir_combo.addItem(
                f"Current: {os.path.basename(current_path) or current_path}",
                current_path,
            )
            self.dir_combo.setCurrentIndex(1)

        for d in scan_dirs:
            if d:
                self.dir_combo.addItem(d, d)
        layout.addWidget(self.dir_combo)

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
        self.export_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.export_btn)

        layout.addLayout(btn_layout)

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
            self.export_btn.setEnabled(True)

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
            "directory": self.dir_combo.currentData(),
            "query": self.query_edit.text(),
            "format": fmt,
            "delimiter": delim,
            "destination": self.dest_edit.text(),
        }
