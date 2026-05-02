import sys
import os
import json

if sys.platform == 'win32':
    import ctypes
    # Simplified ID for better compatibility
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('DirCache.v1')

from PySide6.QtWidgets import QApplication, QMessageBox
from ui.main_window import MainWindow
from database import Database
from scanner import Scanner
from ui.i18n import TRANSLATIONS

CONFIG_FILE = "config.json"

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


from PySide6.QtCore import QThread, Signal

class DirSyncWorker(QThread):
    finished = Signal(str, list)
    def __init__(self, path: str):
        super().__init__()
        self.path = path
    def run(self):
        try:
            entries = []
            for entry in os.scandir(self.path):
                try:
                    s = entry.stat()
                    entries.append({
                        "path": entry.path,
                        "parent": self.path,
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "size": s.st_size if not entry.is_dir() else 0,
                        "mtime": s.st_mtime
                    })
                except OSError:
                    pass
            self.finished.emit(self.path, entries)
        except OSError:
            pass

class PathLogApp:
    def __init__(self):
        from PySide6.QtGui import QIcon, QShortcut, QKeySequence
        from PySide6.QtCore import Qt
        
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("DirCache")
        self.app.setOrganizationName("ZeroTeams")
        
        icon_file = "logo.ico" if os.path.exists(resource_path("logo.ico")) else "logo.png"
        icon_path = resource_path(icon_file)
        
        app_icon = QIcon(icon_path)
        self.app.setWindowIcon(app_icon)
        
        self.window = MainWindow()
        self.window.setWindowIcon(app_icon)
        self.window.setWindowTitle("DirCache Explorer v1.2.0")

        # Shortcuts
        QShortcut(QKeySequence("F11"), self.window, lambda: self.window.showFullScreen() if not self.window.isFullScreen() else self.window.showNormal())
        QShortcut(QKeySequence("Alt+Return"), self.window, lambda: self.window.show_properties())

        self.local_db: Database | None = None
        self.shared_db: Database | None = None
        self.scanner: Scanner | None = None
        self._sync_workers = []

        # Inject data source into explorer table
        self.window.table.set_data_source(self._get_children)
        self.window.table.status_updated.connect(self._on_table_status)
        self.window.table.home_requested.connect(lambda: self.refresh_explorer(force_home=True))
        self.window.target_scan_btn.clicked.connect(lambda: self.start_targeted_scan(self.window.table._current_path))

        self.load_config()

        # Signals
        self.window.scan_btn.clicked.connect(self.start_full_scan)
        self.window.cancel_btn.clicked.connect(self.cancel_scan)
        self.window.search_bar.textChanged.connect(self.search)
        self.window.settings_panel.settings_changed.connect(self.save_config)
        self.window.settings_panel.open_cache_folder_requested.connect(self.open_cache_folder)
        self.window.settings_panel.clear_cache_requested.connect(self.clear_cache)
        self.window.search_shared_cb.stateChanged.connect(lambda: self.search(self.window.search_bar.text()))

        self.refresh_explorer()

    # ── Data source (passed into ExplorerTable) ───────────
    def _is_network_path(self, path: str) -> bool:
        """Returns True if path lives on a network share, not a local physical drive."""
        if not path:
            return False
        # UNC paths (\\server\... or //server/...)
        if path.startswith("\\\\") or path.startswith("//"):
            return True
        # On Windows, check the drive type via Win32 API
        if sys.platform == "win32" and len(path) >= 2 and path[1] == ":":
            try:
                import ctypes
                DRIVE_REMOTE = 4
                drive = path[:3].replace("/", "\\")
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
                return drive_type == DRIVE_REMOTE
            except Exception:
                pass
        return False

    def _get_db_for_path(self, path: str) -> Database | None:
        if not path:
            return None
        # Network paths always go to shared_db (never local_db)
        if self._is_network_path(path):
            return self.shared_db
        return self.local_db

    def _get_children(self, path: str) -> list[dict]:
        db = self._get_db_for_path(path)
        if not db:
            return []
        
        # Start silent background update if local
        if os.path.exists(path) and db == self.local_db:
            # Clean up dead workers
            self._sync_workers = [w for w in self._sync_workers if w.isRunning()]
            worker = DirSyncWorker(path)
            worker.finished.connect(self._on_dir_synced)
            self._sync_workers.append(worker)
            worker.start()
            
        return db.get_children(path)

    def _on_dir_synced(self, path: str, entries: list[dict]):
        db = self._get_db_for_path(path)
        if db:
            db.replace_children(path, entries)
            # If still looking at this folder, update the UI
            if self.window.table._current_path == path and not self.window.search_bar.text():
                # Store selection state if any
                items = db.get_children(path)
                self.window.table._load_items(items)
                n = len(items)
                self.window.table.status_updated.emit(
                    f"{'1 item' if n == 1 else f'{n:,} items'} in this folder.",
                    f"{n:,} items"
                )

    def _on_table_status(self, status: str, count: str):
        self.window.set_status(status)
        self.window.item_count_label.setText(count)
        # Update target scan button visibility/enabled state
        curr = self.window.table._current_path
        self.window.target_scan_btn.setEnabled(bool(curr))

    def _get_local_db_path(self):
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        dir_path = os.path.join(appdata, "DirCache")
        os.makedirs(dir_path, exist_ok=True)
        return os.path.join(dir_path, "local_cache.db")

    def _get_network_db_path(self):
        """Fallback path for network path indexes when no shared_db is configured."""
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        dir_path = os.path.join(appdata, "DirCache")
        os.makedirs(dir_path, exist_ok=True)
        return os.path.join(dir_path, "network_cache.db")

    # ── Config ────────────────────────────────────────────
    def load_config(self):
        local_path = self._get_local_db_path()
        if not os.path.exists(CONFIG_FILE):
            self._init_dbs(local_path, None)
            return
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            
            self.window.settings_panel.blockSignals(True)
            self.window.settings_panel.shared_cache_edit.setText(cfg.get("shared_cache_path", ""))
            
            # Map code back to name for display
            lang_code = cfg.get("language", "en")
            reverse_map = {v: k for k, v in self.window.settings_panel.lang_map.items()}
            self.window.settings_panel.lang_combo.setCurrentText(reverse_map.get(lang_code, "English"))
            
            self.window.settings_panel.theme_combo.setCurrentText(cfg.get("theme", "System Default"))
            self.window.settings_panel.dir_list.clear()
            for d in cfg.get("scan_dirs", []):
                self.window.settings_panel.dir_list.addItem(d)
            self.window.settings_panel.blockSignals(False)
            
            self._init_dbs(local_path, cfg.get("shared_cache_path"))
            self.apply_theme_and_lang()
        except Exception:
            self._init_dbs(local_path, None)
            self.window.settings_panel.blockSignals(False)

    def save_config(self):
        settings = self.window.settings_panel.get_settings()
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception:
            pass
        self._init_dbs(self._get_local_db_path(), settings["shared_cache_path"])
        self.apply_theme_and_lang()
        self.refresh_explorer(force_home=True)

    def apply_theme_and_lang(self):
        settings = self.window.settings_panel.get_settings()
        lang = settings.get("language", "en")
        theme = settings.get("theme", "System Default")
        
        # 1. Update Translations
        t = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
        self.window.update_translations(t)
        
        # 2. Update Theme
        if theme == "System Default":
            # Simple check for Windows Dark Mode
            from PySide6.QtGui import QPalette
            is_dark = QPalette().window().color().lightness() < 128
        else:
            is_dark = (theme == "Dark")
            
        self.window.set_theme(is_dark)

    def _init_dbs(self, local_path: str, shared_path: str):
        if self.local_db: self.local_db.close()
        if self.shared_db: self.shared_db.close()
        
        # local_db: ONLY for physically local drives
        self.local_db = Database(local_path) if local_path else None
        
        # shared_db: ONLY for network paths
        # If user configured a shared SQLite path → use it (multi-user collaboration)
        # Otherwise → private local fallback (network_cache.db, separate from local_cache.db)
        if shared_path:
            self.shared_db = Database(shared_path)
        else:
            self.shared_db = Database(self._get_network_db_path())

        self.scanner = None  # Created fresh per-scan via _scan_sequential

    # ── Scan ──────────────────────────────────────────────
    def start_full_scan(self):
        settings = self.window.settings_panel.get_settings()
        dirs = [d for d in settings["scan_dirs"] if d]
        if not dirs:
            self.window.set_status("Add at least one directory to scan in Settings.")
            return

        self.window.set_progress(True, "Preparing full scan…")
        # For full scan, we should actually split into two scanner runs or one that knows
        # how to pick DB per path. Since current Scanner is simple, we'll just scan all
        # into the appropriate DBs sequentially or together if we upgrade it.
        # Simplest for now: scan everything into their respective DBs.
        
        # Actually, let's update start_targeted_scan and use it for each dir
        # or just run them one by one.
        self._scan_sequential(dirs)

    def _scan_sequential(self, dirs: list[str], total_count: int = 0):
        if not dirs:
            self.on_scan_finished(total_count)
            return
        
        path = dirs[0]
        remaining = dirs[1:]
        db = self._get_db_for_path(path)
        if not db:
            self._scan_sequential(remaining, total_count)
            return

        # Re-init scanner pointing at the correct DB
        self.scanner = Scanner(db)
        self.scanner.start_scan(
            [path],
            progress_callback=lambda p: self.window.set_status(f"Scanning: {p}"),
            finished_callback=lambda count: self._scan_sequential(remaining, total_count + count),
            error_callback=self.on_scan_error,
        )

    def start_targeted_scan(self, path: str):
        db = self._get_db_for_path(path)
        if not path or not db:
            return
        # Silent scan: only show the slim progress bar on the explorer page
        self.window.progress_bar.setVisible(True)
        self.window.target_scan_btn.setEnabled(False)
        self.scanner = Scanner(db)  # Fresh scanner pointing at correct DB
        self.scanner.start_scan(
            [path],
            progress_callback=None,
            finished_callback=self.on_targeted_scan_finished,
            error_callback=self.on_scan_error,
        )

    def on_targeted_scan_finished(self, count: int):
        self.window.progress_bar.setVisible(False)
        self.window.target_scan_btn.setEnabled(True)
        # Just refresh the current view
        self.refresh_explorer()

    def cancel_scan(self):
        if self.scanner:
            self.scanner.stop_scan()
        self.window.set_progress(False, "Scan cancelled.")

    def on_scan_finished(self, count: int):
        self.window.set_progress(False, f"Done — {count:,} items indexed.")
        self.refresh_explorer()

    def on_scan_error(self, message: str):
        self.window.set_progress(False, "Scan failed.")
        # Stop any further sequential scans
        if self.scanner:
            self.scanner.stop_scan()
        QMessageBox.critical(self.window, "Scan Error", f"The scanner process failed to start or crashed.\n\nError: {message}")

    # ── Explorer navigation ───────────────────────────────
    def refresh_explorer(self, force_home=False):
        if not self.local_db and not self.shared_db:
            self.window.set_status("Open Settings to configure directories and cache paths.")
            self.window.item_count_label.setText("")
            return

        settings = self.window.settings_panel.get_settings()
        dirs = [d for d in settings["scan_dirs"] if d]

        if not dirs:
            self.window.set_status("No directories configured — go to Settings.")
            self.window.item_count_label.setText("")
            self.window.table.show_virtual_roots([], label="Indexed Locations")
            return

        # Check if current path is still within configured dirs
        current = self.window.table._current_path
        path_still_valid = False
        if current:
            for d in dirs:
                # Path is valid if it's one of the roots or a child of one
                if current == d or current.startswith(d + os.sep) or current.startswith(d + "/"):
                    path_still_valid = True
                    break
        
        if current and path_still_valid and not force_home:
            self.window.table.navigate_to(current, push_history=False)
            return

        self.window.table.clear_history() # Reset if we go home

        if len(dirs) == 1 and not force_home:
            # Single root → navigate straight into it
            self.window.table.navigate_to(
                dirs[0],
                push_history=False,
            )
        else:
            # Multiple roots or forced home → show virtual list
            virtual_roots = []
            for d in dirs:
                try:
                    stat = os.stat(d)
                    mtime = stat.st_mtime
                except OSError:
                    mtime = 0
                virtual_roots.append({
                    "path": d,
                    "parent": "",
                    "name": os.path.basename(d) or d,
                    "is_dir": True,
                    "size": 0,
                    "mtime": mtime,
                })
            self.window.table.show_virtual_roots(virtual_roots, label="Indexed Locations")

    def search(self, text: str):
        if not self.local_db and not self.shared_db:
            return
        if not text:
            self.refresh_explorer()
            return
        if len(text) < 2:
            return
        # Always search recursively within current dir
        current_path = self.window.table._current_path
        is_global = self.window.search_shared_cb.isChecked()
        settings = self.window.settings_panel.get_settings()
        scan_dirs = [d.replace("\\", "/") for d in settings.get("scan_dirs", []) if d]
        results = []
        seen_paths = set()

        def _add_results(new_results):
            for r in new_results:
                if r["path"] not in seen_paths:
                    seen_paths.add(r["path"])
                    results.append(r)

        if current_path:
            # Scoped: search recursively inside the current directory
            db = self._get_db_for_path(current_path)
            if db:
                _add_results(db.search(text, parent_prefix=current_path))

            # Global: also search every other configured scan dir via correct routing
            if is_global:
                norm_current = current_path.replace("\\", "/")
                for d in scan_dirs:
                    d_norm = d.rstrip("/")
                    if d_norm == norm_current.rstrip("/") or norm_current.startswith(d_norm + "/"):
                        continue  # already covered by current_path scope
                    db = self._get_db_for_path(d)
                    if db:
                        _add_results(db.search(text, parent_prefix=d))
        else:
            # Home view: search all configured dirs, each routed to correct DB
            for d in scan_dirs:
                db = self._get_db_for_path(d)
                if db:
                    _add_results(db.search(text, parent_prefix=d))

            # Global: also search the whole network DB without prefix
            if is_global and self.shared_db:
                _add_results(self.shared_db.search(text))

        self.window.table.set_search_results(results, text)

    def open_cache_folder(self):
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        dir_path = os.path.join(appdata, "DirCache")
        if os.path.exists(dir_path):
            os.startfile(dir_path)

    def clear_cache(self):
        ret = QMessageBox.warning(
            self.window, "Clear Local Cache",
            "⚠️  This will permanently delete all locally indexed file metadata.\n"
            "Network path indexes (network_cache.db or shared DB) are NOT affected.\n\n"
            "This action cannot be undone. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No  # Default to No for safety
        )
        if ret == QMessageBox.Yes:
            if self.local_db:
                self.local_db.close()
                self.local_db = None
            
            path = self._get_local_db_path()
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    QMessageBox.warning(self.window, "Error", f"Could not delete local cache: {e}")
                    return
            
            # Re-init fresh empty local DB (keep shared_db as-is)
            self.local_db = Database(path)
            self.refresh_explorer(force_home=True)
            QMessageBox.information(self.window, "Done", "Local cache cleared successfully.\nNetwork indexes are unchanged.")

    def run(self):
        self.window.show()
        sys.exit(self.app.exec())


if __name__ == "__main__":
    app = PathLogApp()
    app.run()
