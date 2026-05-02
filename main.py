import sys
import os
import json
from PySide6.QtWidgets import QApplication, QMessageBox
from ui.main_window import MainWindow
from database import Database
from scanner import Scanner
from ui.i18n import TRANSLATIONS

CONFIG_FILE = "config.json"


class PathLogApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.window = MainWindow()
        from PySide6.QtGui import QIcon, QShortcut, QKeySequence
        from PySide6.QtCore import Qt
        self.window.setWindowIcon(QIcon("logo.png"))
        self.window.setWindowTitle("DirCache Explorer v1.1.0")
        
        # Win11 Style: Custom title bar requires FramelessWindowHint
        self.window.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.window.setAttribute(Qt.WA_TranslucentBackground)

        # Shortcuts
        QShortcut(QKeySequence("F11"), self.window, lambda: self.window.showFullScreen() if not self.window.isFullScreen() else self.window.showNormal())
        QShortcut(QKeySequence("Alt+Return"), self.window, lambda: self.window.show_properties())

        self.local_db: Database | None = None
        self.shared_db: Database | None = None
        self.scanner: Scanner | None = None

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

        self.refresh_explorer()

    # ── Data source (passed into ExplorerTable) ───────────
    def _get_db_for_path(self, path: str) -> Database | None:
        if not path:
            return None
        # Use shared_db if it's a network path AND shared_db exists
        if (path.startswith("\\\\") or path.startswith("//")) and self.shared_db:
            return self.shared_db
        # Fallback to local_db for everything else
        return self.local_db

    def _get_children(self, path: str) -> list[dict]:
        db = self._get_db_for_path(path)
        if not db:
            return []
        return db.get_children(path)

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
        
        self.local_db = Database(local_path) if local_path else None
        self.shared_db = Database(shared_path) if shared_path else None
        
        # Scanner needs one DB as primary, but we'll re-init it per-scan
        # so we'll just keep a placeholder or re-assign
        self.scanner = Scanner(self.local_db or self.shared_db) if (self.local_db or self.shared_db) else None

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

    def _scan_sequential(self, dirs: list[str]):
        if not dirs:
            self.on_scan_finished(0) # Not accurate count but stops UI
            return
        
        path = dirs[0]
        db = self._get_db_for_path(path)
        if not db:
            self._scan_sequential(dirs[1:])
            return
            
        self.scanner.db = db # Point to correct DB
        self.scanner.start_scan(
            [path],
            progress_callback=lambda p: self.window.set_status(f"Scanning: {p}"),
            finished_callback=lambda _: self._scan_sequential(dirs[1:]),
            error_callback=self.on_scan_error,
        )

    def start_targeted_scan(self, path: str):
        db = self._get_db_for_path(path)
        if not path or not self.scanner or not db:
            return
        # Silent scan: only show the slim progress bar on the explorer page
        self.window.progress_bar.setVisible(True)
        self.window.target_scan_btn.setEnabled(False)
        self.scanner.db = db # Point to correct DB
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
        
        # Scoped search if we are in a directory
        current_path = self.window.table._current_path
        results = []
        if current_path:
            db = self._get_db_for_path(current_path)
            if db:
                results = db.search(text, parent_prefix=current_path)
        else:
            # Global search across all active DBs
            if self.local_db:
                results.extend(self.local_db.search(text))
            if self.shared_db:
                results.extend(self.shared_db.search(text))
        
        self.window.table.set_search_results(results, text)

    def run(self):
        self.window.show()
        sys.exit(self.app.exec())


if __name__ == "__main__":
    app = PathLogApp()
    app.run()
