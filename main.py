import sys
import os
import json
from PySide6.QtWidgets import QApplication, QMessageBox
from ui.main_window import MainWindow
from database import Database
from scanner import Scanner

CONFIG_FILE = "config.json"


class PathLogApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.window = MainWindow()
        from PySide6.QtGui import QIcon
        self.window.setWindowIcon(QIcon("logo.png"))

        self.db: Database | None = None
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
    def _get_children(self, path: str) -> list[dict]:
        if not self.db:
            return []
        return self.db.get_children(path)

    def _on_table_status(self, status: str, count: str):
        self.window.set_status(status)
        self.window.item_count_label.setText(count)
        # Update target scan button visibility/enabled state
        curr = self.window.table._current_path
        self.window.target_scan_btn.setEnabled(bool(curr))

    # ── Config ────────────────────────────────────────────
    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
            self.window.settings_panel.cache_path_edit.setText(cfg.get("cache_path", ""))
            for d in cfg.get("scan_dirs", []):
                self.window.settings_panel.dir_list.addItem(d)
            if cfg.get("cache_path"):
                self._init_db(cfg["cache_path"])
        except Exception:
            pass

    def save_config(self):
        settings = self.window.settings_panel.get_settings()
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception:
            pass
        if settings["cache_path"]:
            self._init_db(settings["cache_path"])
        self.refresh_explorer()

    def _init_db(self, path: str):
        if self.db:
            self.db.close()
        self.db = Database(path)
        self.scanner = Scanner(self.db)

    # ── Scan ──────────────────────────────────────────────
    def start_full_scan(self):
        settings = self.window.settings_panel.get_settings()
        if not settings["scan_dirs"]:
            self.window.set_status("Add at least one directory to scan in Settings.")
            return
        if not settings["cache_path"]:
            self.window.set_status("Set a cache database path in Settings.")
            return

        self.window.set_progress(True, "Preparing scan…")
        self.scanner.start_scan(
            settings["scan_dirs"],
            progress_callback=lambda p: self.window.set_status(f"Scanning: {p}"),
            finished_callback=self.on_scan_finished,
            error_callback=self.on_scan_error,
        )

    def start_targeted_scan(self, path: str):
        if not path or not self.scanner:
            return
        # Silent scan: only show the slim progress bar on the explorer page
        self.window.progress_bar.setVisible(True)
        self.window.target_scan_btn.setEnabled(False)
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
        QMessageBox.critical(self.window, "Scan Error", message)

    # ── Explorer navigation ───────────────────────────────
    def refresh_explorer(self, force_home=False):
        if not self.db:
            self.window.set_status("Open Settings to configure directories and a cache path.")
            self.window.item_count_label.setText("")
            return

        settings = self.window.settings_panel.get_settings()
        dirs = [d for d in settings["scan_dirs"] if d]

        if not dirs:
            self.window.set_status("No directories configured — go to Settings.")
            self.window.item_count_label.setText("")
            return

        # If we are already in a folder, just refresh its content
        current = self.window.table._current_path
        if current and not force_home:
            self.window.table.navigate_to(current, push_history=False)
            return

        if len(dirs) == 1 and not force_home:
            # Single root → navigate straight into it
            self.window.table.navigate_to(
                dirs[0],
                root_label=os.path.basename(dirs[0]) or dirs[0],
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
        if not self.db:
            return
        if not text:
            self.refresh_explorer()
            return
        if len(text) < 2:
            return
        
        # Scoped search if we are in a directory
        current_path = self.window.table._current_path
        results = self.db.search(text, parent_prefix=current_path if current_path else None)
        self.window.table.set_search_results(results, text)

    def run(self):
        self.window.show()
        sys.exit(self.app.exec())


if __name__ == "__main__":
    app = PathLogApp()
    app.run()
