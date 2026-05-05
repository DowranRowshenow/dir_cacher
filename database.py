import sqlite3
import os
from typing import List, Optional, Dict


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30000)
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA synchronous = NORMAL;")
        self.conn.execute("PRAGMA busy_timeout = 30000;")
        self.conn.execute("PRAGMA page_size = 4096;")
        self.conn.execute("PRAGMA cache_size = -8000;")  # 8 MB page cache
        self.create_tables()

    def create_tables(self):
        with self.conn:
            # Minimal schema — WITHOUT ROWID saves ~8 bytes/row for TEXT PKs
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    path   TEXT PRIMARY KEY,
                    parent TEXT NOT NULL DEFAULT '',
                    name   TEXT NOT NULL DEFAULT '',
                    is_dir INTEGER NOT NULL DEFAULT 0,
                    size   INTEGER NOT NULL DEFAULT 0
                ) WITHOUT ROWID
                """
            )
            # Composite index: covers get_children (parent filter + dir-first sort)
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_parent ON entries(parent, is_dir, name)"
            )
            # Separate name index: covers LIKE/GLOB text search
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_name ON entries(name)"
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_status (
                    root_path TEXT PRIMARY KEY,
                    last_scan REAL
                ) WITHOUT ROWID
                """
            )
        self._migrate()

    def _migrate(self):
        """Migrate legacy schema (had mtime/ctime/author) to minimal schema."""
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(entries)")
        cols = {row[1] for row in cursor.fetchall()}

        if "mtime" in cols:
            # Old schema detected — recreate table without heavy columns
            try:
                with self.conn:
                    self.conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS entries_new (
                            path   TEXT PRIMARY KEY,
                            parent TEXT NOT NULL DEFAULT '',
                            name   TEXT NOT NULL DEFAULT '',
                            is_dir INTEGER NOT NULL DEFAULT 0,
                            size   INTEGER NOT NULL DEFAULT 0
                        ) WITHOUT ROWID
                        """
                    )
                    self.conn.execute(
                        """
                        INSERT OR IGNORE INTO entries_new (path, parent, name, is_dir, size)
                        SELECT path,
                               COALESCE(parent, ''),
                               COALESCE(name, ''),
                               COALESCE(is_dir, 0),
                               COALESCE(size, 0)
                        FROM entries
                        """
                    )
                    self.conn.execute("DROP TABLE entries")
                    self.conn.execute("ALTER TABLE entries_new RENAME TO entries")
                    self.conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_parent ON entries(parent, is_dir, name)"
                    )
                    self.conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_name ON entries(name)"
                    )
                # Reclaim freed pages immediately
                self.conn.execute("VACUUM")
            except Exception:
                pass  # If migration fails, existing DB still works

    # ── Write ─────────────────────────────────────────────
    def upsert_entries(self, entries: List[Dict]):
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO entries (path, parent, name, is_dir, size)
                VALUES (:path, :parent, :name, :is_dir, :size)
                ON CONFLICT(path) DO UPDATE SET
                    parent = excluded.parent,
                    name   = excluded.name,
                    is_dir = excluded.is_dir,
                    size   = excluded.size
                """,
                entries,
            )

    def replace_children(self, parent_path: str, entries: List[Dict]):
        with self.conn:
            self.conn.execute("DELETE FROM entries WHERE parent = ?", (parent_path,))
            if entries:
                self.conn.executemany(
                    """
                    INSERT INTO entries (path, parent, name, is_dir, size)
                    VALUES (:path, :parent, :name, :is_dir, :size)
                    """,
                    entries,
                )

    # ── Read ──────────────────────────────────────────────
    def get_children(
        self,
        parent_path: str,
        file_types: List[str] = None,
        min_mtime: float = 0,
        max_mtime: float = 0,
    ) -> List[Dict]:
        sql = "SELECT path, parent, name, is_dir, size FROM entries WHERE parent = ?"
        params = [parent_path]

        if file_types:
            exts = []
            for ft in file_types:
                exts.extend(self._get_exts_for_type(ft))
            if exts:
                sql += (
                    " AND (is_dir = 1 OR ("
                    + " OR ".join(["name LIKE ?" for _ in exts])
                    + "))"
                )
                params.extend([f"%.{e}" for e in exts])

        sql += " ORDER BY is_dir DESC, name ASC LIMIT 5000"
        cursor = self.conn.execute(sql, params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

        # Enrich with real-time stat (mtime/ctime/size from disk)
        needs_date_filter = min_mtime > 0 or max_mtime > 0
        out = []
        for row in rows:
            st = self._stat(row["path"])
            row["mtime"] = st[0]
            row["ctime"] = st[1]
            if st[2]:                    # update size from disk if available
                row["size"] = st[2]
            if needs_date_filter and not row["is_dir"]:
                if min_mtime > 0 and row["mtime"] < min_mtime:
                    continue
                if max_mtime > 0 and row["mtime"] > max_mtime:
                    continue
            out.append(row)
        return out

    def search(
        self,
        query: str,
        parent_prefix: Optional[str] = None,
        file_types: List[str] = None,
        min_mtime: float = 0,
        max_mtime: float = 0,
        case_sensitive: bool = False,
    ) -> List[Dict]:
        terms = [t.strip() for t in query.split("&") if t.strip()]
        if not terms and not file_types and min_mtime == 0:
            return []

        op = "GLOB" if case_sensitive else "LIKE"
        sql = "SELECT path, parent, name, is_dir, size FROM entries WHERE 1=1"
        params = []

        for term in terms:
            sql += f" AND name {op} ?"
            params.append(f"*{term}*" if case_sensitive else f"%{term}%")

        if file_types:
            exts = []
            for ft in file_types:
                exts.extend(self._get_exts_for_type(ft))
            if exts:
                sql += (
                    " AND (is_dir = 1 OR ("
                    + " OR ".join(["name LIKE ?" for _ in exts])
                    + "))"
                )
                params.extend([f"%.{e}" for e in exts])

        if parent_prefix:
            p = parent_prefix.replace("\\", "/").rstrip("/")
            sql += " AND (replace(path,'\\','/') = ? OR replace(path,'\\','/') LIKE ?)"
            params.append(p)
            params.append(f"{p}/%")

        sql += " LIMIT 2000"
        cursor = self.conn.execute(sql, params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

        # Real-time mtime only if date filter is active
        needs_date_filter = min_mtime > 0 or max_mtime > 0
        out = []
        for row in rows:
            st = self._stat(row["path"])
            row["mtime"] = st[0]
            row["ctime"] = st[1]
            if needs_date_filter and not row["is_dir"]:
                if min_mtime > 0 and row["mtime"] < min_mtime:
                    continue
                if max_mtime > 0 and row["mtime"] > max_mtime:
                    continue
            out.append(row)
        return out

    # ── Helpers ───────────────────────────────────────────
    def _stat(self, path: str):
        """Returns (mtime, ctime, size) from disk, or (0, 0, 0) on error."""
        try:
            s = os.stat(path)
            return s.st_mtime, s.st_ctime, s.st_size
        except OSError:
            return 0.0, 0.0, 0

    def _get_exts_for_type(self, file_type: str) -> List[str]:
        mapping = {
            "Excel":       ["xlsx", "xls", "csv", "xlsm"],
            "PDF":         ["pdf"],
            "Word":        ["docx", "doc", "rtf"],
            "Drawings":    ["dwg", "dxf"],
            "Images":      ["png", "jpg", "jpeg", "gif", "bmp", "svg", "webp"],
            "Archives":    ["zip", "rar", "7z", "tar", "gz"],
            "Executables": ["exe", "msi", "bat", "cmd"],
        }
        return mapping.get(file_type, [])

    def update_scan_status(self, root_path: str, timestamp: float):
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO scan_status (root_path, last_scan)
                VALUES (?, ?)
                ON CONFLICT(root_path) DO UPDATE SET last_scan = excluded.last_scan
                """,
                (root_path, timestamp),
            )

    def get_scan_status(self, root_path: str) -> Optional[float]:
        cursor = self.conn.execute(
            "SELECT last_scan FROM scan_status WHERE root_path = ?", (root_path,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def get_item_count(self, root_path: str) -> int:
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM entries WHERE path = ? OR path LIKE ? || '/%' OR path LIKE ? || '\\%'",
            (root_path, root_path, root_path),
        )
        return cursor.fetchone()[0]

    def close(self):
        self.conn.close()
