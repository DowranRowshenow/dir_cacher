from PySide6.QtCore import QObject, Signal, QThread
import os
import sys
import sqlite3
import time
from database import Database

class ScanWorker(QObject):
    progress = Signal(str)
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, db_path: str, root_paths: list[str]):
        super().__init__()
        self.db_path = db_path
        self.root_paths = root_paths
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            # Private connection for the thread to avoid locking the UI
            conn = sqlite3.connect(self.db_path, timeout=30000)
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA busy_timeout = 30000")
            
            total = 0
            batch = []
            
            for root_dir in self.root_paths:
                if self._is_cancelled: break
                stack = [root_dir]
                
                while stack and not self._is_cancelled:
                    curr = stack.pop()
                    try:
                        with os.scandir(curr) as it:
                            for entry in it:
                                if self._is_cancelled: break
                                try:
                                    is_dir = entry.is_dir(follow_symlinks=False)
                                    stat = entry.stat(follow_symlinks=False)
                                    
                                    batch.append((
                                        entry.path, curr, entry.name,
                                        is_dir, stat.st_size, stat.st_mtime
                                    ))
                                    total += 1
                                    
                                    if is_dir:
                                        stack.append(entry.path)
                                        
                                    if len(batch) >= 500:
                                        self._flush(conn, batch)
                                        batch = []
                                        self.progress.emit(f"Indexed {total} items...")
                                        
                                except (PermissionError, OSError): continue
                    except (PermissionError, OSError): continue
                        
            if batch:
                self._flush(conn, batch)
                
            conn.close()
            self.finished.emit(total)
        except Exception as e:
            self.error.emit(str(e))

    def _flush(self, conn, batch):
        with conn:
            conn.executemany("""
                INSERT INTO entries (path, parent, name, is_dir, size, mtime)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    size=excluded.size, mtime=excluded.mtime
            """, batch)

class Scanner(QObject):
    progress = Signal(str)
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._thread = None
        self._worker = None

    def start_scan(self, root_paths: list[str], progress_callback=None, finished_callback=None, error_callback=None):
        if self._thread and self._thread.isRunning():
            return

        self._thread = QThread()
        self._worker = ScanWorker(self.db.db_path, root_paths)
        self._worker.moveToThread(self._thread)
        
        self._thread.started.connect(self._worker.run)
        
        # Safe signal connections
        if progress_callback: self.progress.connect(progress_callback)
        if finished_callback: self.finished.connect(finished_callback)
        if error_callback:    self.error.connect(error_callback)
        
        self._worker.progress.connect(self.progress.emit)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.error.connect(self.error.emit)
        
        self._thread.start()

    def _on_worker_finished(self, count):
        self.finished.emit(count)
        self._cleanup()

    def _cleanup(self):
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        
        # Safely disconnect external listeners
        try:
            self.progress.disconnect()
            self.finished.disconnect()
            self.error.disconnect()
        except:
            pass

    def stop_scan(self):
        if self._worker:
            self._worker.cancel()
        self._cleanup()
