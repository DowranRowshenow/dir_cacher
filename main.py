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
        self.window.table.scan_requested.connect(lambda path: self.start_targeted_scan(path, recursive=False))
        self.window.target_scan_btn.clicked.connect(lambda: self.start_targeted_scan(self.window.table._current_path))

        self.load_config()

        # Connect Filters
        self.window.filter_changed.connect(self._on_filter_changed)

        self.window.scan_btn.clicked.connect(self.start_full_scan)
        self.window.cancel_btn.clicked.connect(self.cancel_scan)
        self.window.dir_scan_requested.connect(self.start_targeted_scan)
        self.window.dir_cancel_requested.connect(self.cancel_targeted_scan)
        self.window.dir_pause_requested.connect(self.pause_targeted_scan)
        self.window.dir_pause_requested.connect(self.pause_targeted_scan)
        self.active_scanners = {}
        
        from PySide6.QtCore import QTimer
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300)
        self.search_timer.timeout.connect(lambda: self.search(self.window.search_bar.text()))
        self.window.search_bar.textChanged.connect(self.search_timer.start)
        
        self.window.settings_panel.settings_changed.connect(self.save_config)
        self.window.settings_panel.open_cache_folder_requested.connect(self.open_cache_folder)
        self.window.settings_panel.clear_cache_requested.connect(self.clear_cache)
        self.window.search_shared_cb.stateChanged.connect(lambda: self.search(self.window.search_bar.text()))
        self.window.export_btn.clicked.connect(self.open_export_wizard)

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
        
        # Silently refresh the folder in the background (no UI blocking, no progress bar)
        if os.path.exists(path):
            self._silent_scan(path)
            
        file_types, min_mtime, max_mtime = self._get_filter_params()
        return db.get_children(path, file_types=file_types, min_mtime=min_mtime, max_mtime=max_mtime)

    def _on_table_status(self, status: str, count: str):
        self.window.set_status(status)
        self.window.item_count_label.setText(count)
        # Update target scan button visibility/enabled state
        curr = self.window.table._current_path
        self.window.target_scan_btn.setEnabled(bool(curr))

    def open_export_wizard(self):
        from ui.export_dialog import ExportDialog
        from PySide6.QtWidgets import QMessageBox
        from ui.i18n import TRANSLATIONS
        
        settings = self.window.settings_panel.get_settings()
        scan_dirs = settings.get("scan_dirs", [])
        lang = settings.get("language", "en")
        t = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
        
        dialog = ExportDialog(scan_dirs, self.window.is_dark, t, self.window)
        # Pre-fill query with current search bar content
        dialog.query_edit.setText(self.window.search_bar.text())
        
        if dialog.exec():
            params = dialog.get_export_params()
            target_dir = params["directory"]
            query = params["query"]
            fmt = params["format"]
            dest = params["destination"]
            
            try:
                self._export_data(target_dir, query, fmt, dest)
                msg = QMessageBox(self.window)
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("Export Success")
                msg.setText(f"Successfully exported data to:\n{dest}")
                if self.window.is_dark:
                    from ui.styles import apply_dark_title_bar
                    msg.setStyleSheet("QMessageBox { background-color: #1e1e1e; color: #ffffff; } QLabel { color: #ffffff; } QPushButton { background-color: #333333; color: #ffffff; border: 1px solid #555555; padding: 4px 16px; border-radius: 4px; } QPushButton:hover { background-color: #444444; }")
                    msg.show() # Must be shown to have a window handle
                    apply_dark_title_bar(msg, True)
                msg.exec()
            except Exception as e:
                msg = QMessageBox(self.window)
                msg.setIcon(QMessageBox.Critical)
                msg.setWindowTitle("Export Error")
                msg.setText(f"Failed to export data:\n{e}")
                if self.window.is_dark:
                    from ui.styles import apply_dark_title_bar
                    msg.setStyleSheet("QMessageBox { background-color: #1e1e1e; color: #ffffff; } QLabel { color: #ffffff; } QPushButton { background-color: #333333; color: #ffffff; border: 1px solid #555555; padding: 4px 16px; border-radius: 4px; } QPushButton:hover { background-color: #444444; }")
                    msg.show()
                    apply_dark_title_bar(msg, True)
                msg.exec()

    def _export_data(self, target_dir, query, fmt, dest):
        results = []
        
        def _fetch_from_db(db, t_dir):
            if not db: return
            conn = db.conn
            cursor = conn.cursor()
            sql = "SELECT path, parent, name, is_dir, size FROM entries"
            params = []
            
            conditions = []
            if t_dir:
                p = t_dir.replace("\\", "/").rstrip("/")
                conditions.append("(replace(path, '\\', '/') = ? OR replace(path, '\\', '/') LIKE ?)")
                params.extend([p, f"{p}/%"])
                
            if query:
                terms = [t.strip() for t in query.split("&") if t.strip()]
                for term in terms:
                    conditions.append("name LIKE ?")
                    params.append(f"%{term}%")
                    
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
                
            cursor.execute(sql, params)
            import os
            for row in cursor.fetchall():
                path = row[0]
                try:
                    mtime = os.stat(path).st_mtime
                except OSError:
                    mtime = 0
                results.append({
                    "Path": path,
                    "Parent": row[1],
                    "Name": row[2],
                    "Is Directory": "Yes" if row[3] else "No",
                    "Size (Bytes)": row[4],
                    "Modified Time": mtime
                })

        if target_dir:
            _fetch_from_db(self._get_db_for_path(target_dir), target_dir)
        else:
            _fetch_from_db(self.local_db, None)
            _fetch_from_db(self.shared_db, None)
            
        import csv
        from datetime import datetime

        if fmt == "csv":
            with open(dest, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=["Path", "Parent", "Name", "Is Directory", "Size (Bytes)", "Modified Time"])
                writer.writeheader()
                for r in results:
                    mtime = r["Modified Time"]
                    r["Modified Time"] = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S') if mtime else ""
                    writer.writerow(r)
        elif fmt == "xlsx":
            try:
                import openpyxl
            except ImportError:
                raise Exception("openpyxl is not installed. Run 'pip install openpyxl'.")
            
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Exported Data"
            
            headers = ["Path", "Parent", "Name", "Is Directory", "Size (Bytes)", "Modified Time"]
            ws.append(headers)
            
            for r in results:
                mtime = r["Modified Time"]
                mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S') if mtime else ""
                ws.append([
                    r["Path"], r["Parent"], r["Name"], r["Is Directory"], r["Size (Bytes)"], mtime_str
                ])
                
            wb.save(dest)

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
            
            theme_val = cfg.get("theme", "System Default")
            theme_idx = ["System Default", "Light", "Dark"].index(theme_val) if theme_val in ["System Default", "Light", "Dark"] else 0
            self.window.settings_panel.theme_combo.setCurrentIndex(theme_idx)
            self.window.settings_panel.dir_list.clear()
            for d in cfg.get("scan_dirs", []):
                self.window.settings_panel.dir_list.addItem(d)
            self.window.settings_panel.blockSignals(False)
            
            # Collect scan info with timestamps
            self._init_dbs(local_path, cfg.get("shared_cache_path"))
            
            self._update_scan_ui()
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
        
        self._update_scan_ui()
        self.apply_theme_and_lang()
        self.refresh_explorer(force_home=True)

    def _update_scan_ui(self):
        settings = self.window.settings_panel.get_settings()
        dir_infos = []
        for d in settings.get("scan_dirs", []):
            db = self._get_db_for_path(d)
            last_scan = db.get_scan_status(d) if db else None
            item_count = db.get_item_count(d) if db else 0
            dir_infos.append({
                "path": d, 
                "last_scan": last_scan,
                "item_count": item_count
            })
            
        self.window.update_scan_dirs(dir_infos)

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

        def _on_progress(msg):
            self.window.set_status(f"Scanning: {path} - {msg}")
            self.window.set_dir_scan_state(path, True, msg)

        def _on_finish(count):
            import time
            db.update_scan_status(path, time.time())
            if path in self.active_scanners:
                del self.active_scanners[path]
            self._update_scan_ui()
            self._scan_sequential(remaining, total_count + count)

        scanner = Scanner(db)
        self.active_scanners[path] = scanner
        self.window.set_dir_scan_state(path, True, "Starting...")
        scanner.start_scan(
            [path],
            progress_callback=_on_progress,
            finished_callback=_on_finish,
            error_callback=self.on_scan_error,
        )

    def _silent_scan(self, path: str):
        """Non-recursive background scan triggered when opening a folder.
        Completely silent — no progress bar, no UI blocking, no re-navigation on finish.
        Skipped if a scan for this path is already running."""
        db = self._get_db_for_path(path)
        if not path or not db:
            return
        if path in self.active_scanners:
            return  # Already scanning this path, don't queue another

        def _on_finish(count):
            import time
            db.update_scan_status(path, time.time())
            if path in self.active_scanners:
                del self.active_scanners[path]
            # Silently update the scan page cards
            self._update_scan_ui()
            
            # If the user is still looking at this folder, update the table view directly
            # This avoids calling refresh_explorer() and causing an infinite scan loop.
            if self.window.table._current_path == path:
                file_types, min_mtime, max_mtime = self._get_filter_params()
                items = db.get_children(path, file_types=file_types, min_mtime=min_mtime, max_mtime=max_mtime)
                # Ensure we apply the current search text filter if any
                search_text = self.window.search_bar.text().strip()
                if search_text:
                    # If we are searching, we shouldn't just show children.
                    # We should probably call search() again if we want to update search results.
                    # But _silent_scan is not recursive, so it won't affect global search much.
                    pass
                else:
                    self.window.table._highlight_delegate.set_query("")
                    self.window.table._load_items(items)
                    n = len(items)
                    self.window.table.status_updated.emit(
                        f"{'1 item' if n == 1 else f'{n:,} items'} in this folder.", f"{n:,} items"
                    )

        def _on_error(msg):
            if path in self.active_scanners:
                del self.active_scanners[path]

        scanner = Scanner(db)
        self.active_scanners[path] = scanner
        scanner.start_scan(
            [path],
            progress_callback=None,   # Silent — no status updates
            finished_callback=_on_finish,
            error_callback=_on_error,
            recursive=False           # Always shallow for folder-open
        )

    def start_targeted_scan(self, path: str, recursive: bool = True):
        """Explicit user-triggered scan (from context menu or scan button).
        Shows progress bar, updates UI, and refreshes the table when done."""
        db = self._get_db_for_path(path)
        if not path or not db:
            return
            
        if path in self.active_scanners:
            return
            
        self.window.progress_bar.setVisible(True)
        self.window.set_dir_scan_state(path, True, "Starting...")
        
        def _on_progress(msg):
            self.window.set_dir_scan_state(path, True, msg)
            
        def _on_finish(count):
            import time
            db.update_scan_status(path, time.time())
            if path in self.active_scanners:
                del self.active_scanners[path]
            self.on_targeted_scan_finished(count)

        def _on_error(msg):
            if path in self.active_scanners:
                del self.active_scanners[path]
            self._update_scan_ui()
            self.on_scan_error(msg)

        scanner = Scanner(db)
        self.active_scanners[path] = scanner
        scanner.start_scan(
            [path],
            progress_callback=_on_progress,
            finished_callback=_on_finish,
            error_callback=_on_error,
            recursive=recursive
        )

    def cancel_targeted_scan(self, path: str):
        if path in self.active_scanners:
            self.active_scanners[path].stop_scan()
            del self.active_scanners[path]
        self._update_scan_ui()

    def pause_targeted_scan(self, path: str, is_paused: bool):
        if path in self.active_scanners:
            scanner = self.active_scanners[path]
            if is_paused:
                scanner.pause_scan()
                self.window.set_dir_scan_state(path, True, "Paused")
            else:
                scanner.resume_scan()
                self.window.set_dir_scan_state(path, True, "Resuming...")

    def on_targeted_scan_finished(self, count: int):
        self.window.progress_bar.setVisible(False)
        self.window.set_status(f"Scan complete — {count:,} items indexed.")
        self._update_scan_ui()
        # Refresh the currently visible folder without re-triggering a silent scan
        current = self.window.table._current_path
        if current:
            self.window.table.navigate_to(current, push_history=False)
        else:
            self.refresh_explorer()

    def cancel_scan(self):
        for scanner in self.active_scanners.values():
            scanner.stop_scan()
        self.active_scanners.clear()
        self.window.set_progress(False, "Scan cancelled.")
        self._update_scan_ui()

    def on_scan_finished(self, count: int):
        self.window.set_progress(False, f"Done — {count:,} items indexed.")
        self._update_scan_ui()
        self.refresh_explorer()

    def on_scan_error(self, message: str):
        self.window.set_progress(False, "Scan failed.")
        for scanner in self.active_scanners.values():
            scanner.stop_scan()
        self.active_scanners.clear()
        self._update_scan_ui()
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(self.window, "Scan Error", f"The scanner process failed to start or crashed.\n\nError: {message}")

    # ── Explorer navigation ───────────────────────────────
    def _on_filter_changed(self):
        # If filters are active, we treat it like a search (recursive)
        # Even if search text is empty
        self.refresh_explorer()

    def _get_filter_params(self):
        file_types = []
        for name, cb in self.window.type_checkboxes.items():
            if cb.isChecked():
                file_types.append(name)
        
        date_text = self.window.date_filter.currentText()
        
        import time
        from datetime import datetime, timedelta
        
        min_mtime = 0
        max_mtime = 0
        now = datetime.now()
        
        if date_text == "Today":
            min_mtime = datetime(now.year, now.month, now.day).timestamp()
        elif date_text == "Last 7 Days":
            min_mtime = (now - timedelta(days=7)).timestamp()
        elif date_text == "Last 30 Days":
            min_mtime = (now - timedelta(days=30)).timestamp()
        elif date_text == "This Year":
            min_mtime = datetime(now.year, 1, 1).timestamp()
        # If the last item is selected, it's the custom range
        last_idx = self.window.date_filter.count() - 1
        if self.window.date_filter.currentIndex() == last_idx and self.window.custom_date_range:
            min_mtime, max_mtime = self.window.custom_date_range
            
        return file_types, min_mtime, max_mtime

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

        # Check if we should use search mode (recursive) vs browse mode (immediate children)
        search_text = self.window.search_bar.text().strip()
        file_types, min_mtime, max_mtime = self._get_filter_params()
        
        # User requested: "just show only matching types in current dir table. not whole search"
        # So filters ALONE do not trigger search mode.
        is_searching = bool(search_text)

        if is_searching and not force_home:
            self.search(search_text)
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
        
        file_types, min_mtime, max_mtime = self._get_filter_params()
        
        # If no text AND no filters, go back to browsing
        if not text and not file_types and min_mtime == 0 and max_mtime == 0:
            self.refresh_explorer()
            return
            
        # Always search recursively within current dir
        current_path = self.window.table._current_path
        is_global = self.window.search_shared_cb.isChecked()
        is_case = self.window.case_sensitive_cb.isChecked()
        settings = self.window.settings_panel.get_settings()
        scan_dirs = [d.replace("\\", "/") for d in settings.get("scan_dirs", []) if d]
        results = []
        seen_paths = set()

        def _add_results(new_results):
            for r in new_results:
                if r["path"] not in seen_paths:
                    seen_paths.add(r["path"])
                    results.append(r)

        file_types, min_mtime, max_mtime = self._get_filter_params()

        if current_path:
            # Scoped: search recursively inside the current directory
            db = self._get_db_for_path(current_path)
            if db:
                _add_results(db.search(text, parent_prefix=current_path, file_types=file_types, min_mtime=min_mtime, max_mtime=max_mtime, case_sensitive=is_case))

            # Global: also search every other configured scan dir via correct routing
            if is_global:
                norm_current = current_path.replace("\\", "/")
                for d in scan_dirs:
                    d_norm = d.rstrip("/")
                    if d_norm == norm_current.rstrip("/") or norm_current.startswith(d_norm + "/"):
                        continue  # already covered by current_path scope
                    db = self._get_db_for_path(d)
                    if db:
                        _add_results(db.search(text, parent_prefix=d, file_types=file_types, min_mtime=min_mtime, max_mtime=max_mtime, case_sensitive=is_case))
        else:
            # Home view: search all configured dirs, each routed to correct DB
            for d in scan_dirs:
                db = self._get_db_for_path(d)
                if db:
                    _add_results(db.search(text, parent_prefix=d, file_types=file_types, min_mtime=min_mtime, max_mtime=max_mtime, case_sensitive=is_case))

            # Global: also search the whole network DB without prefix
            if is_global and self.shared_db:
                _add_results(self.shared_db.search(text, file_types=file_types, min_mtime=min_mtime, max_mtime=max_mtime, case_sensitive=is_case))

        self.window.table.set_search_results(results, text)

    def open_cache_folder(self):
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        dir_path = os.path.join(appdata, "DirCache")
        if os.path.exists(dir_path):
            os.startfile(dir_path)

    def clear_cache(self):
        msg = QMessageBox(self.window)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Clear Local Cache")
        msg.setText(
            "⚠️  This will permanently delete all locally indexed file metadata.\n"
            "Network path indexes (network_cache.db or shared DB) are NOT affected.\n\n"
            "This action cannot be undone. Continue?"
        )
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        
        if self.window.is_dark:
            from ui.styles import apply_dark_title_bar
            msg.setStyleSheet("QMessageBox { background-color: #1e1e1e; color: #ffffff; } QLabel { color: #ffffff; } QPushButton { background-color: #333333; color: #ffffff; border: 1px solid #555555; padding: 4px 16px; border-radius: 4px; } QPushButton:hover { background-color: #444444; }")
            msg.show()
            apply_dark_title_bar(msg, True)

        ret = msg.exec()
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
            
            done_msg = QMessageBox(self.window)
            done_msg.setWindowTitle("Done")
            done_msg.setText("Local cache cleared successfully.\nNetwork indexes are unchanged.")
            if self.window.is_dark:
                from ui.styles import apply_dark_title_bar
                done_msg.setStyleSheet("QMessageBox { background-color: #1e1e1e; color: #ffffff; } QLabel { color: #ffffff; } QPushButton { background-color: #333333; color: #ffffff; border: 1px solid #555555; padding: 4px 16px; border-radius: 4px; } QPushButton:hover { background-color: #444444; }")
                done_msg.show()
                apply_dark_title_bar(done_msg, True)
            done_msg.exec()

    def run(self):
        self.window.show()
        sys.exit(self.app.exec())


if __name__ == "__main__":
    app = PathLogApp()
    app.run()
