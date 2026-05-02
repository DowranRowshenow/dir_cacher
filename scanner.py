from PySide6.QtCore import QObject, Signal, QThread
import os
import sys
import sqlite3
import ctypes
from ctypes import c_char_p, c_int, c_int64, c_double, c_void_p, CFUNCTYPE

# Locate the Rust DLL
def _get_dll_path():
    if hasattr(sys, '_MEIPASS'):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    dll_name = "scanner_core.dll" if sys.platform == "win32" else "libscanner_core.so"
    
    # Try local dev path first
    dev_path = os.path.join(base_dir, "scanner_core", "target", "release", dll_name)
    if os.path.exists(dev_path):
        return dev_path
    return os.path.join(base_dir, dll_name)

try:
    _scanner_lib = ctypes.CDLL(_get_dll_path())
    
    _scanner_lib.create_cancel_flag.restype = c_void_p
    _scanner_lib.cancel_scan.argtypes = [c_void_p]
    _scanner_lib.free_cancel_flag.argtypes = [c_void_p]
    
    ENTRY_CALLBACK = CFUNCTYPE(None, c_char_p, c_char_p, c_char_p, c_int, c_int64, c_double)
    _scanner_lib.scan_directory.argtypes = [c_char_p, c_void_p, ENTRY_CALLBACK]
    _scanner_lib.scan_directory.restype = c_int64
except Exception:
    _scanner_lib = None


class ScanWorker(QObject):
    progress = Signal(str)
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, db_path: str, root_paths: list[str]):
        super().__init__()
        self.db_path = db_path
        self.root_paths = root_paths
        if _scanner_lib:
            self._cancel_flag = _scanner_lib.create_cancel_flag()
        else:
            self._cancel_flag = None
            self._is_cancelled = False

    def cancel(self):
        if self._cancel_flag:
            _scanner_lib.cancel_scan(self._cancel_flag)
        else:
            self._is_cancelled = True

    def __del__(self):
        if self._cancel_flag:
            _scanner_lib.free_cancel_flag(self._cancel_flag)

    def run(self):
        try:
            conn = sqlite3.connect(self.db_path, timeout=30000)
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA busy_timeout = 30000")
            
            total = [0]
            batch = []
            
            def _entry_callback(path_p, parent_p, name_p, is_dir, size, mtime):
                try:
                    path = path_p.decode('utf-8')
                    parent = parent_p.decode('utf-8')
                    name = name_p.decode('utf-8')
                    batch.append((path, parent, name, is_dir, size, mtime))
                    total[0] += 1
                    if len(batch) >= 500:
                        self._flush(conn, batch)
                        self.progress.emit(f"Indexed {total[0]} items...")
                except Exception:
                    pass

            # Fallback to Python if DLL didn't load
            if not _scanner_lib:
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
                                            int(is_dir), stat.st_size, stat.st_mtime
                                        ))
                                        total[0] += 1
                                        if is_dir:
                                            stack.append(entry.path)
                                        if len(batch) >= 500:
                                            self._flush(conn, batch)
                                            self.progress.emit(f"Indexed {total[0]} items...")
                                    except (PermissionError, OSError): continue
                        except (PermissionError, OSError): continue
            else:
                # Use Rust DLL
                c_callback = ENTRY_CALLBACK(_entry_callback)
                for root_dir in self.root_paths:
                    c_root = root_dir.encode('utf-8')
                    _scanner_lib.scan_directory(c_root, self._cancel_flag, c_callback)

            if batch:
                self._flush(conn, batch)
                
            conn.close()
            self.finished.emit(total[0])
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
        batch.clear()

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
