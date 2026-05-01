import os
import time
from typing import Callable, Optional
from PySide6.QtCore import QObject, Signal, QThread
from database import Database

class ScanWorker(QObject):
    progress = Signal(str)  # Current directory being scanned
    finished = Signal(int)  # Total items scanned
    error = Signal(str)

    def __init__(self, db: Database, root_paths: list[str]):
        super().__init__()
        self.db = db
        self.root_paths = root_paths
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        total_items = 0
        batch = []
        stack = list(self.root_paths)
        
        try:
            while stack and not self._is_cancelled:
                current_root = stack.pop()
                self.progress.emit(current_root)
                
                try:
                    with os.scandir(current_root) as it:
                        for entry in it:
                            if self._is_cancelled:
                                break
                            
                            try:
                                stat = entry.stat(follow_symlinks=False)
                                item = {
                                    "path": entry.path,
                                    "parent": current_root,
                                    "name": entry.name,
                                    "is_dir": entry.is_dir(),
                                    "size": stat.st_size,
                                    "mtime": stat.st_mtime
                                }
                                batch.append(item)
                                total_items += 1
                                
                                if entry.is_dir(follow_symlinks=False):
                                    stack.append(entry.path)
                                    
                                if len(batch) >= 500: # Larger batch for better performance
                                    self.db.upsert_entries(batch)
                                    batch = []
                                    self.progress.emit(f"Indexed {total_items} items...")
                                    
                            except (PermissionError, OSError) as e:
                                continue
                except (PermissionError, OSError) as e:
                    continue
                    
            if batch:
                self.db.upsert_entries(batch)
            
            self.finished.emit(total_items)
        except Exception as e:
            import traceback
            self.error.emit(f"Critical error during scan: {str(e)}\n{traceback.format_exc()}")

class Scanner(QObject):
    # This class acts as the interface that will eventually wrap the Rust backend
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.thread = None
        self.worker = None

    def start_scan(self, root_paths: list[str], progress_callback, finished_callback, error_callback):
        self.thread = QThread()
        self.worker = ScanWorker(self.db, root_paths)
        self.worker.moveToThread(self.thread)
        
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(progress_callback)
        self.worker.finished.connect(finished_callback)
        self.worker.error.connect(error_callback)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.thread.start()

    def stop_scan(self):
        if self.worker:
            self.worker.cancel()
