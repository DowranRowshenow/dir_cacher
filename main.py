import sys
import os
import json

if sys.platform == "win32":
    import ctypes

    # Simplified ID for better compatibility
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DirCache.v1")

from PySide6.QtWidgets import QApplication, QMessageBox
from ui.main_window import MainWindow
from database import Database
from scanner import Scanner
from ui.i18n import TRANSLATIONS
from ui.export_progress import ExportProgressDialog

CONFIG_FILE = "config.json"


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


from PySide6.QtCore import QThread, Signal, QTimer


class SearchWorker(QThread):
    finished = Signal(list, str, int) # results, query, offset
    progress = Signal(int, int)
    def __init__(
        self,
        dbs_to_search,
        text,
        file_types,
        min_mtime,
        max_mtime,
        is_case,
        parent_prefixes,
        delimiter="&",
        wildcard_char="*",
        limit=1000,
        offset=0,
    ):
        super().__init__()
        self.dbs_to_search = dbs_to_search
        self.text = text
        self.file_types = file_types
        self.min_mtime = min_mtime
        self.max_mtime = max_mtime
        self.is_case = is_case
        self.parent_prefixes = parent_prefixes
        self.delimiter = delimiter
        self.wildcard_char = wildcard_char
        self.limit = limit
        self.offset = offset

    def run(self):
        results = []
        seen_paths = set()
        is_sql = self.text.lower().startswith("sql:")
        query = self.text[4:].strip() if is_sql else self.text

        for i, db in enumerate(self.dbs_to_search):
            if is_sql:
                res = db.raw_sql_search(query)
            else:
                prefix = (
                    self.parent_prefixes[i] if i < len(self.parent_prefixes) else None
                )
                res = db.search(
                    query,
                    parent_prefix=prefix,
                    file_types=self.file_types,
                    min_mtime=self.min_mtime,
                    max_mtime=self.max_mtime,
                    case_sensitive=self.is_case,
                    delimiter=self.delimiter,
                    wildcard_char=self.wildcard_char,
                    limit=self.limit,
                    offset=self.offset,
                )

            for r in res:
                path = r.get("path")
                if path and path not in seen_paths:
                    seen_paths.add(path)
                    results.append(r)
                elif not path:  # Handle error messages or pathless results
                    results.append(r)
            self.progress.emit(i + 1, len(self.dbs_to_search))
        self.finished.emit(results, self.text, self.offset)

    def finished_emit(self, results, text, offset):
        # Helper to avoid signal signature mismatch if any
        self.finished.emit(results, text, offset)


class ExportWorker(QThread):
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(int, str)  # value, text

    def __init__(self, logic_fn, target_dir, query, fmt, dest, delimiter=","):
        super().__init__()
        self.logic_fn = logic_fn
        self.target_dir = target_dir
        self.query = query
        self.fmt = fmt
        self.dest = dest
        self.delimiter = delimiter
        self._is_canceled = False

    def stop(self):
        self._is_canceled = True

    def run(self):
        try:

            def progress_cb(v, t):
                self.progress.emit(v, t)

            def cancel_check():
                return self._is_canceled

            self.logic_fn(
                self.target_dir,
                self.query,
                self.fmt,
                self.dest,
                self.delimiter,
                progress_cb,
                cancel_check,
            )
            if not self._is_canceled:
                self.finished.emit(self.dest)
        except Exception as e:
            if not self._is_canceled:
                self.error.emit(str(e))


class PathLogApp:
    def __init__(self):
        from PySide6.QtGui import QIcon, QShortcut, QKeySequence
        from PySide6.QtCore import Qt

        # High DPI support for sharp fonts
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

        self.app = QApplication(sys.argv)
        self.app.setApplicationName("DirCache")
        self.app.setOrganizationName("ZeroTeams")

        icon_file = (
            "logo.ico" if os.path.exists(resource_path("logo.ico")) else "logo.png"
        )
        icon_path = resource_path(icon_file)

        app_icon = QIcon(icon_path)
        self.app.setWindowIcon(app_icon)

        self.window = MainWindow()
        self.window.setWindowIcon(app_icon)
        self.window.setWindowTitle("DirCache Explorer v1.2.0")

        # Shortcuts
        QShortcut(
            QKeySequence("F11"),
            self.window,
            lambda: (
                self.window.showFullScreen()
                if not self.window.isFullScreen()
                else self.window.showNormal()
            ),
        )
        QShortcut(
            QKeySequence("Alt+Return"),
            self.window,
            lambda: self.window.show_properties(),
        )

        self.local_db: Database | None = None
        self.shared_db: Database | None = None
        self.scanner: Scanner | None = None
        self._sync_workers = []

        # Connect DB sync helpers
        self.window.table.set_data_source(
            self._get_children,
            rename_entry_fn=self._on_db_rename,
            delete_entry_fn=self._on_db_delete,
        )
        self.window.table.status_updated.connect(self._on_table_status)
        self.window.table.home_requested.connect(
            lambda: self.refresh_explorer(force_home=True)
        )
        self.window.table.scan_requested.connect(
            lambda path: self.start_targeted_scan(path, recursive=False)
        )
        self.window.target_scan_btn.clicked.connect(
            lambda: self.start_targeted_scan(self.window.table._current_path)
        )

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
        self.search_timer.timeout.connect(
            lambda: self.search(self.window.search_bar.text())
        )
        self.window.search_bar.textChanged.connect(self.search_timer.start)
        self.window.table.load_more_requested.connect(self.search)

        self.window.settings_panel.settings_changed.connect(self.save_config)
        self.window.settings_panel.open_cache_folder_requested.connect(
            self.open_cache_folder
        )
        self.window.settings_panel.clear_cache_requested.connect(self.clear_cache)
        self.window.export_btn.clicked.connect(self.open_export_wizard)
        self.search_worker = None

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

    def _get_children(self, path: str, limit: int = 1000, offset: int = 0) -> list[dict]:
        db = self._get_db_for_path(path)
        if not db:
            return []

        # Silently refresh the folder in the background (no UI blocking, no progress bar)
        if os.path.exists(path) and offset == 0:
            self._silent_scan(path)

        file_types, min_mtime, max_mtime = self._get_filter_params()
        return db.get_children(
            path, file_types=file_types, min_mtime=min_mtime, max_mtime=max_mtime,
            limit=limit, offset=offset
        )

    def _on_table_status(self, status: str, count: str):
        self.window.set_status(status)
        self.window.item_count_label.setText(count)
        # Update target scan button visibility/enabled state
        curr = self.window.table._current_path
        self.window.target_scan_btn.setEnabled(bool(curr))

    def open_export_wizard(self):
        from ui.export_dialog import ExportDialog
        from ui.i18n import TRANSLATIONS

        settings = self.window.settings_panel.get_settings()
        scan_dirs = settings.get("scan_dirs", [])
        lang = settings.get("language", "en")
        t = TRANSLATIONS.get(lang, TRANSLATIONS["en"])

        dialog = ExportDialog(
            scan_dirs,
            self.window.table._current_path,
            self.window.is_dark,
            t,
            self.window,
        )
        dialog.query_edit.setText(self.window.search_bar.text())

        if dialog.exec():
            params = dialog.get_export_params()

            # Progress dialog
            self.export_prog = ExportProgressDialog(self.window.is_dark, t, self.window)

            self.export_worker = ExportWorker(
                self._export_data_logic,
                params["directory"],
                params["query"],
                params["format"],
                params["destination"],
                params.get("delimiter", ","),
            )

            self.export_prog.canceled.connect(self.export_worker.stop)
            self.export_worker.progress.connect(self.export_prog.set_progress)
            self.export_worker.finished.connect(
                lambda d: (self.export_prog.accept(), self.on_export_finished(d))
            )
            self.export_worker.error.connect(
                lambda e: (self.export_prog.reject(), self.on_export_error(e))
            )

            self.export_worker.start()
            self.export_prog.exec()

    def on_export_finished(self, dest):
        from PySide6.QtWidgets import QMessageBox

        self.window.set_scanning(False)
        self.window.set_status("Ready")

        msg = QMessageBox(self.window)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Export Success")
        msg.setText(f"Successfully exported data to:\n{dest}")
        if self.window.is_dark:
            from ui.styles import apply_dark_title_bar

            msg.setStyleSheet(
                "QMessageBox { background-color: #1e1e1e; color: #ffffff; } QLabel { color: #ffffff; } QPushButton { background-color: #333333; color: #ffffff; border: 1px solid #555555; padding: 4px 16px; border-radius: 4px; } QPushButton:hover { background-color: #444444; }"
            )
            msg.show()
            apply_dark_title_bar(msg, True)
        msg.exec()

    def on_export_error(self, err):
        from PySide6.QtWidgets import QMessageBox

        self.window.set_scanning(False)
        self.window.set_status("Export Failed")

        msg = QMessageBox(self.window)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Export Error")
        msg.setText(f"Failed to export data:\n{err}")
        if self.window.is_dark:
            from ui.styles import apply_dark_title_bar

            msg.setStyleSheet(
                "QMessageBox { background-color: #1e1e1e; color: #ffffff; } QLabel { color: #ffffff; } QPushButton { background-color: #333333; color: #ffffff; border: 1px solid #555555; padding: 4px 16px; border-radius: 4px; } QPushButton:hover { background-color: #444444; }"
            )
            msg.show()
            apply_dark_title_bar(msg, True)
        msg.exec()

    def _export_data_logic(
        self, target_dir, query, fmt, dest, delimiter=",", progress_cb=None, cancel_check=None
    ):
        results = []

        if progress_cb:
            progress_cb(5, "Querying database...")

        def _fetch_from_db(db, t_dir):
            if not db:
                return
            if cancel_check and cancel_check():
                return

            conn = db.conn
            cursor = conn.cursor()
            sql = "SELECT d.path as parent, e.name, e.is_dir, e.size FROM entries e JOIN directories d ON e.parent_id = d.id"
            params = []

            conditions = []
            if t_dir:
                p = t_dir.replace("\\", "/").rstrip("/")
                conditions.append(
                    "(replace(d.path, '\\', '/') = ? OR replace(d.path, '\\', '/') LIKE ?)"
                )
                params.extend([p, f"{p}/%"])

            if query:
                terms = [t.strip() for t in query.split("&") if t.strip()]
                for term in terms:
                    conditions.append("e.name LIKE ?")
                    params.append(f"%{term}%")

            if conditions:
                sql += " WHERE " + " AND ".join(conditions)

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            total = len(rows)
            for i, row in enumerate(rows):
                if cancel_check and cancel_check():
                    break
                if progress_cb and i % 500 == 0:
                    progress_cb(
                        10 + int(40 * (i / total)), f"Processing items... ({i}/{total})"
                    )

                parent = row[0]
                name = row[1]
                sep = "\\" if "\\" in parent else "/"
                path = (
                    parent + sep + name if not parent.endswith(sep) else parent + name
                )

                # We skip os.stat during export to keep it fast, or only do it if requested.
                # User said "Exporting takes long time than normal", likely due to os.stat on network shares.
                # We'll use 0 or skip it for now.
                results.append(
                    {
                        "Path": path,
                        "Parent": parent,
                        "Name": name,
                        "Is Directory": "Yes" if row[2] else "No",
                        "Size (Bytes)": row[3],
                        "Modified Time": 0,
                    }
                )

        if target_dir:
            _fetch_from_db(self._get_db_for_path(target_dir), target_dir)
        else:
            _fetch_from_db(self.local_db, None)
            _fetch_from_db(self.shared_db, None)

        if cancel_check and cancel_check():
            return

        if progress_cb:
            progress_cb(55, f"Writing to {fmt.upper()}...")

        import csv
        from datetime import datetime

        if fmt in ["csv", "txt"]:
            with open(dest, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "Path",
                        "Parent",
                        "Name",
                        "Is Directory",
                        "Size (Bytes)",
                        "Modified Time",
                    ],
                    delimiter=delimiter,
                )
                writer.writeheader()
                total = len(results)
                for i, r in enumerate(results):
                    if cancel_check and cancel_check():
                        break
                    if progress_cb and i % 1000 == 0:
                        progress_cb(
                            60 + int(35 * (i / total)), f"Writing rows... {i}/{total}"
                        )

                    # Modified Time is 0 now
                    r["Modified Time"] = ""
                    writer.writerow(r)
        elif fmt == "xlsx":
            try:
                import openpyxl
            except ImportError:
                raise Exception(
                    "openpyxl is not installed. Run 'pip install openpyxl'."
                )

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Exported Data"

            headers = [
                "Path",
                "Parent",
                "Name",
                "Is Directory",
                "Size (Bytes)",
                "Modified Time",
            ]
            ws.append(headers)

            total = len(results)
            for i, r in enumerate(results):
                if cancel_check and cancel_check():
                    break
                if progress_cb and i % 500 == 0:
                    progress_cb(
                        60 + int(35 * (i / total)), f"Writing to Excel... {i}/{total}"
                    )

                ws.append(
                    [
                        r["Path"],
                        r["Parent"],
                        r["Name"],
                        r["Is Directory"],
                        r["Size (Bytes)"],
                        "",
                    ]
                )

            if not (cancel_check and cancel_check()):
                wb.save(dest)

        if progress_cb:
            progress_cb(100, "Done!")

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
            self.window.settings_panel.shared_cache_edit.setText(
                cfg.get("shared_cache_path", "")
            )

            # Map code back to name for display
            lang_code = cfg.get("language", "en")
            reverse_map = {v: k for k, v in self.window.settings_panel.lang_map.items()}
            self.window.settings_panel.lang_combo.setCurrentText(
                reverse_map.get(lang_code, "English")
            )

            theme_val = cfg.get("theme", "System Default")
            theme_idx = (
                ["System Default", "Light", "Dark"].index(theme_val)
                if theme_val in ["System Default", "Light", "Dark"]
                else 0
            )
            self.window.settings_panel.theme_combo.setCurrentIndex(theme_idx)
            self.window.settings_panel.dir_list.clear()
            for d in cfg.get("scan_dirs", []):
                self.window.settings_panel.dir_list.addItem(d)

            self.window.settings_panel.delim_edit.setText(
                cfg.get("search_delimiter", "&")
            )
            self.search_delimiter = cfg.get("search_delimiter", "&")
            self.window.settings_panel.wildcard_edit.setText(
                cfg.get("wildcard_char", "*")
            )
            self.wildcard_char = cfg.get("wildcard_char", "*")

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
        self.search_delimiter = settings.get("search_delimiter", "&")
        self.wildcard_char = settings.get("wildcard_char", "*")
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
        scan_dirs = settings.get("scan_dirs", [])
        dir_infos = []
        for d in scan_dirs:
            db = self._get_db_for_path(d)
            last_scan = db.get_scan_status(d) if db else None
            item_count = db.get_item_count(d) if db else 0
            dir_infos.append(
                {"path": d, "last_scan": last_scan, "item_count": item_count}
            )

        self.window.update_scan_dirs(dir_infos)

        # Only update checkboxes if they have changed to avoid resetting user selection
        existing = list(self.window.location_checkboxes.keys())
        if set(existing) != set(scan_dirs):
            self.window.update_search_locations(scan_dirs)

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
            is_dark = theme == "Dark"

        self.window.set_theme(is_dark)

    def _init_dbs(self, local_path: str, shared_path: str):
        if self.local_db:
            self.local_db.close()
        if self.shared_db:
            self.shared_db.close()

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
        self.window.set_progress(True, "Preparing full scan…")
        self.window.set_scanning(True)
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
        self.window.set_scanning(True)
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
        if not db:
            return

        if path in self.active_scanners:
            self.window.table.set_scanning(True)
            return  # Already scanning this path, don't queue another

        self.window.table.set_scanning(True)

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
                self.window.table.set_scanning(False)
                file_types, min_mtime, max_mtime = self._get_filter_params()
                items = db.get_children(
                    path,
                    file_types=file_types,
                    min_mtime=min_mtime,
                    max_mtime=max_mtime,
                )
                
                # Only update UI if the scan found new/changed items compared to cache
                current = getattr(self.window.table, "_current_items", [])
                changed = True
                if current and items:
                    changed = (items != current[:len(items)])
                elif not current and not items:
                    changed = False

                # Ensure we apply the current search text filter if any
                search_text = self.window.search_bar.text().strip()
                if changed and not search_text:
                    self.window.table._highlight_delegate.set_query("")
                    self.window.table._load_items(items)
                    n = len(items)
                    self.window.table.status_updated.emit(
                        f"{'1 item' if n == 1 else f'{n:,} items'} in this folder.",
                        f"{n:,} items",
                    )
            elif not self.active_scanners:
                self.window.table.set_scanning(False)

        def _on_error(msg):
            if path in self.active_scanners:
                del self.active_scanners[path]
            if self.window.table._current_path == path:
                self.window.table.set_scanning(False)

        scanner = Scanner(db)
        self.active_scanners[path] = scanner
        scanner.start_scan(
            [path],
            progress_callback=None,  # Silent — no status updates
            finished_callback=_on_finish,
            error_callback=_on_error,
            recursive=False,  # Always shallow for folder-open
        )

    def start_targeted_scan(self, path: str, recursive: bool = True):
        """Explicit user-triggered scan (from context menu or scan button).
        Shows progress bar, updates UI, and refreshes the table when done."""
        db = self._get_db_for_path(path)
        if not path or not db:
            return

        if path in self.active_scanners:
            return

        self.window.set_scanning(True)
        self.window.progress_bar.setVisible(True)
        self.window.set_dir_scan_state(path, True, "Starting...")

        def _on_progress(msg):
            self.window.set_dir_scan_state(path, True, msg)

        def _on_finish(count):
            import time

            db.update_scan_status(path, time.time())
            if path in self.active_scanners:
                del self.active_scanners[path]
            self.window.set_scanning(False)
            self.on_targeted_scan_finished(count)

        def _on_error(msg):
            if path in self.active_scanners:
                del self.active_scanners[path]
            self.window.set_scanning(False)
            self._update_scan_ui()
            self.on_scan_error(msg)

        scanner = Scanner(db)
        self.active_scanners[path] = scanner
        scanner.start_scan(
            [path],
            progress_callback=_on_progress,
            finished_callback=_on_finish,
            error_callback=_on_error,
            recursive=recursive,
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
        self.window.set_scanning(False)
        self.window.set_progress(False, "Scan cancelled.")
        self._update_scan_ui()

    def on_search_worker_finished(self, results, query, offset=0):
        self.window.set_scanning(False)
        self.window.table.set_search_results(results, query, offset=offset)
        self._update_scan_ui()

    def on_scan_finished(self, total_count):
        self.window.set_scanning(False)
        self.window.set_progress(False, f"Scan complete. Found {total_count:,} items.")
        self._update_scan_ui()
        self.refresh_explorer()

    def on_scan_error(self, message: str):
        self.window.set_scanning(False)
        self.window.set_progress(False, "Scan failed.")
        for scanner in self.active_scanners.values():
            scanner.stop_scan()
        self.active_scanners.clear()
        self._update_scan_ui()
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(
            self.window,
            "Scan Error",
            f"The scanner process failed to start or crashed.\n\nError: {message}",
        )

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

        idx = self.window.date_filter.currentIndex()
        
        import time
        from datetime import datetime, timedelta

        min_mtime = 0
        max_mtime = 0
        now = datetime.now()

        if idx == 1:  # Today
            min_mtime = datetime(now.year, now.month, now.day).timestamp()
        elif idx == 2:  # Last week
            min_mtime = (now - timedelta(days=7)).timestamp()
        elif idx == 3:  # Last month
            min_mtime = (now - timedelta(days=30)).timestamp()
        elif idx == 4:  # This Year
            min_mtime = datetime(now.year, 1, 1).timestamp()
        elif idx == self.window.date_filter.count() - 1:  # Custom Range
            if self.window.custom_date_range:
                min_mtime, max_mtime = self.window.custom_date_range

        return file_types, min_mtime, max_mtime

    def refresh_explorer(self, force_home=False):
        if not self.local_db and not self.shared_db:
            self.window.set_status(
                "Open Settings to configure directories and cache paths."
            )
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
                if (
                    current == d
                    or current.startswith(d + os.sep)
                    or current.startswith(d + "/")
                ):
                    path_still_valid = True
                    break

        if current and path_still_valid and not force_home:
            self.window.table.navigate_to(current, push_history=False)
            return

        self.window.table.clear_history()  # Reset if we go home

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
                virtual_roots.append(
                    {
                        "path": d,
                        "parent": "",
                        "name": os.path.basename(d) or d,
                        "is_dir": True,
                        "size": 0,
                        "mtime": mtime,
                    }
                )
            self.window.table.show_virtual_roots(
                virtual_roots, label="Indexed Locations"
            )

    def search(self, text: str, offset: int = 0, limit: int = 1000):
        if not self.local_db and not self.shared_db:
            return

        file_types, min_mtime, max_mtime = self._get_filter_params()

        # If no text AND no filters, go back to browsing
        if not text and not file_types and min_mtime == 0 and max_mtime == 0:
            self.refresh_explorer()
            return

        is_case = self.window.case_sensitive_cb.isChecked()

        # Determine exactly which databases and prefixes to search
        dbs_to_search = []
        prefixes = []

        checked_locations = [
            loc for loc, cb in self.window.location_checkboxes.items() if cb.isChecked()
        ]
        if checked_locations:
            scope = checked_locations
        else:
            scope = [
                d
                for d in self.window.settings_panel.get_settings().get("scan_dirs", [])
                if d
            ]

        for loc in scope:
            db = self._get_db_for_path(loc)
            if db:
                dbs_to_search.append(db)
                prefixes.append(loc)

        if not dbs_to_search:
            return

        self.window.set_scanning(True)

        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.terminate()

        self.search_worker = SearchWorker(
            dbs_to_search,
            text,
            file_types,
            min_mtime,
            max_mtime,
            is_case,
            prefixes,
            getattr(self, "search_delimiter", "&"),
            getattr(self, "wildcard_char", "*"),
            limit=limit,
            offset=offset,
        )
        self.search_worker.progress.connect(self._on_search_progress)
        self.search_worker.finished.connect(self.on_search_worker_finished)
        self.search_worker.start()
        self.window.set_status("Searching...")

    def _on_search_progress(self, current, total):
        pct = int((current / total) * 100) if total > 0 else 0
        self.window.set_status(f"Searching... {pct}% ({current}/{total} locations)")

    def on_search_worker_finished(self, results, original_text):
        self.window.set_scanning(False)
        # Ensure we only show results for the LATEST search query
        if self.window.search_bar.text() != original_text:
            return
        self.window.table.show_search_results(results, original_text)
        self.window.set_status(f'Found {len(results):,} items for "{original_text}".')

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

            msg.setStyleSheet(
                "QMessageBox { background-color: #1e1e1e; color: #ffffff; } QLabel { color: #ffffff; } QPushButton { background-color: #333333; color: #ffffff; border: 1px solid #555555; padding: 4px 16px; border-radius: 4px; } QPushButton:hover { background-color: #444444; }"
            )
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
                    QMessageBox.warning(
                        self.window, "Error", f"Could not delete local cache: {e}"
                    )
                    return

            # Re-init fresh empty local DB (keep shared_db as-is)
            self.local_db = Database(path)
            self.refresh_explorer(force_home=True)

            done_msg = QMessageBox(self.window)
            done_msg.setWindowTitle("Done")
            done_msg.setText(
                "Local cache cleared successfully.\nNetwork indexes are unchanged."
            )
            if self.window.is_dark:
                from ui.styles import apply_dark_title_bar

                done_msg.setStyleSheet(
                    "QMessageBox { background-color: #1e1e1e; color: #ffffff; } QLabel { color: #ffffff; } QPushButton { background-color: #333333; color: #ffffff; border: 1px solid #555555; padding: 4px 16px; border-radius: 4px; } QPushButton:hover { background-color: #444444; }"
                )
                done_msg.show()
                apply_dark_title_bar(done_msg, True)
            done_msg.exec()

    def run(self):
        self.window.show()
        sys.exit(self.app.exec())

    def _on_db_rename(self, old_path, new_path):
        db = self._get_db_for_path(old_path)
        if db:
            db.rename_entry(old_path, new_path)

    def _on_db_delete(self, path):
        db = self._get_db_for_path(path)
        if db:
            db.delete_entry(path)


if __name__ == "__main__":
    app = PathLogApp()
    app.run()
