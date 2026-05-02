import os
import time
from typing import Callable, Optional
from PySide6.QtCore import QObject, Signal, QThread
from database import Database

from PySide6.QtCore import QObject, Signal, QProcess
import sys

class Scanner(QObject):
    progress = Signal(str)
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.process = None

    def start_scan(self, root_paths: list[str], progress_callback=None, finished_callback=None, error_callback=None):
        if self.process and self.process.state() != QProcess.NotRunning:
            return

        self.process = QProcess()
        
        # Connect callbacks
        if progress_callback: self.progress.connect(progress_callback)
        if finished_callback: self.finished.connect(finished_callback)
        if error_callback:    self.error.connect(error_callback)

        self.process.readyReadStandardOutput.connect(self._handle_output)
        self.process.finished.connect(self._on_finished)
        
        args = [sys.executable, "scanner_cli.py", self.db.db_path] + root_paths
        self.process.start(sys.executable, args[1:])

    def _handle_output(self):
        while self.process.canReadLine():
            line = self.process.readLine().data().decode().strip()
            if line.startswith("PROGRESS:"):
                count = line.split(":")[1]
                self.progress.emit(f"Indexed {count} items...")
            elif line.startswith("START:"):
                path = line.split(":")[1]
                self.progress.emit(f"Scanning: {path}")

    def _on_finished(self):
        output = self.process.readAllStandardOutput().data().decode()
        total = 0
        for line in output.splitlines():
            if line.startswith("DONE:"):
                total = int(line.split(":")[1])
        
        # Clean up signals for next run
        try:
            self.finished.emit(total)
            self.progress.disconnect()
            self.finished.disconnect()
            self.error.disconnect()
        except: pass

    def stop_scan(self):
        if self.process:
            self.process.kill()
