import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QProgressBar, QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal

class ExportProgressDialog(QDialog):
    canceled = Signal()

    def __init__(self, is_dark, t, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t.get("export_wizard", "Export Progress"))
        self.setFixedSize(400, 150)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

        if is_dark:
            from ui.styles import apply_dark_title_bar
            self.show()
            apply_dark_title_bar(self, True)
        
        bg = "#1e1e1e" if is_dark else "#ffffff"
        fg = "#ffffff" if is_dark else "#1a1a1a"
        border = "#333333" if is_dark else "#cccccc"
        
        self.setStyleSheet(f"""
            QDialog {{ background: {bg}; color: {fg}; }}
            QLabel {{ color: {fg}; font-size: 13px; }}
            QProgressBar {{
                border: 1px solid {border};
                border-radius: 4px;
                text-align: center;
                background: {bg};
                color: {fg};
            }}
            QProgressBar::chunk {{
                background-color: #0078d4;
                border-radius: 2px;
            }}
            QPushButton {{
                background: {'#333333' if is_dark else '#f0f0f0'};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 6px 20px;
                color: {fg};
            }}
            QPushButton:hover {{ background: {'#444444' if is_dark else '#e0e0e0'}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 20)

        self.status_lbl = QLabel("Starting export...")
        layout.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.cancel_btn = QPushButton(t.get("cancel", "Cancel"))
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def _on_cancel(self):
        self.canceled.emit()
        self.reject()

    def set_progress(self, value, text=None):
        self.progress_bar.setValue(value)
        if text:
            self.status_lbl.setText(text)
