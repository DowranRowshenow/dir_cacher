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
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS directories (
                    id INTEGER PRIMARY KEY,
                    path TEXT UNIQUE NOT NULL
                )
                """
            )
            # Minimal schema — WITHOUT ROWID saves space, using parent_id eliminates redundant paths
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    parent_id INTEGER NOT NULL,
                    name   TEXT NOT NULL,
                    is_dir INTEGER NOT NULL DEFAULT 0,
                    size   INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (parent_id, name)
                ) WITHOUT ROWID
                """
            )
        self._migrate()
        
        with self.conn:
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entries_parent_dir ON entries(parent_id, is_dir, name)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entries_name ON entries(name)"
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_status (
                    root_path TEXT PRIMARY KEY,
                    last_scan REAL
                ) WITHOUT ROWID
                """
            )

    def _migrate(self):
        """Migrate legacy schema (flat path/parent) to relation schema (directories/entries)."""
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(entries)")
        cols = {row[1] for row in cursor.fetchall()}

        if "path" in cols:
            # Old schema detected — perform data migration
            try:
                with self.conn:
                    self.conn.execute("BEGIN TRANSACTION")
                    
                    # 1. Ensure new tables exist (done in create_tables)
                    # 2. Rename old table
                    self.conn.execute("ALTER TABLE entries RENAME TO old_entries")
                    
                    # 3. Create fresh entries table
                    self.conn.execute(
                        """
                        CREATE TABLE entries (
                            parent_id INTEGER NOT NULL,
                            name   TEXT NOT NULL,
                            is_dir INTEGER NOT NULL DEFAULT 0,
                            size   INTEGER NOT NULL DEFAULT 0,
                            PRIMARY KEY (parent_id, name)
                        ) WITHOUT ROWID
                        """
                    )
                    
                    # 4. Extract unique parent paths
                    self.conn.execute(
                        "INSERT OR IGNORE INTO directories (path) SELECT DISTINCT parent FROM old_entries WHERE parent != ''"
                    )
                    
                    # 5. Insert mapped data
                    self.conn.execute(
                        """
                        INSERT OR IGNORE INTO entries (parent_id, name, is_dir, size)
                        SELECT d.id, o.name, o.is_dir, o.size
                        FROM old_entries o
                        JOIN directories d ON d.path = o.parent
                        """
                    )
                    
                    # 6. Drop old table
                    self.conn.execute("DROP TABLE old_entries")
                    
                    # 7. Recreate indexes
                    self.conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_parent_dir ON entries(parent_id, is_dir, name)")
                    self.conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_name ON entries(name)")
                    
                    self.conn.execute("COMMIT")
                    
                # Reclaim freed pages immediately
                self.conn.execute("VACUUM")
            except Exception as e:
                try:
                    self.conn.execute("ROLLBACK")
                except: pass
                # If migration fails, we are in a broken state potentially. 
                pass

    # ── Write ─────────────────────────────────────────────
    def upsert_entries(self, entries: List[Dict]):
        if not entries: return
        
        # Collect unique parents
        parents = list({e["parent"] for e in entries if e["parent"] is not None})
        
        with self.conn:
            # 1. Ensure parents exist
            self.conn.executemany(
                "INSERT OR IGNORE INTO directories (path) VALUES (?)",
                [(p,) for p in parents]
            )
            
            # 2. Get parent IDs
            parent_ids = {}
            # Chunking to avoid 999 max variable limit
            for i in range(0, len(parents), 900):
                chunk = parents[i:i+900]
                placeholders = ",".join(["?"] * len(chunk))
                cursor = self.conn.execute(
                    f"SELECT path, id FROM directories WHERE path IN ({placeholders})", chunk
                )
                for path, row_id in cursor.fetchall():
                    parent_ids[path] = row_id
            
            # 3. Map entries and execute
            items = []
            for e in entries:
                pid = parent_ids.get(e["parent"])
                if pid is not None:
                    items.append((pid, e["name"], e["is_dir"], e["size"]))
            
            self.conn.executemany(
                """
                INSERT INTO entries (parent_id, name, is_dir, size)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(parent_id, name) DO UPDATE SET
                    is_dir = excluded.is_dir,
                    size   = excluded.size
                """,
                items,
            )

    def replace_children(self, parent_path: str, entries: List[Dict]):
        with self.conn:
            # 1. Get or create parent_id
            cursor = self.conn.execute("SELECT id FROM directories WHERE path = ?", (parent_path,))
            row = cursor.fetchone()
            if not row:
                self.conn.execute("INSERT INTO directories (path) VALUES (?)", (parent_path,))
                parent_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            else:
                parent_id = row[0]

            # 2. Delete old
            self.conn.execute("DELETE FROM entries WHERE parent_id = ?", (parent_id,))
            
            # 3. Insert new
            if entries:
                items = [(parent_id, e["name"], e["is_dir"], e["size"]) for e in entries]
                self.conn.executemany(
                    """
                    INSERT INTO entries (parent_id, name, is_dir, size)
                    VALUES (?, ?, ?, ?)
                    """,
                    items,
                )

    # ── Read ──────────────────────────────────────────────
    def get_children(
        self,
        parent_path: str,
        file_types: List[str] = None,
        min_mtime: float = 0,
        max_mtime: float = 0,
    ) -> List[Dict]:
        cursor = self.conn.execute("SELECT id FROM directories WHERE path = ?", (parent_path,))
        row = cursor.fetchone()
        if not row:
            return []
        parent_id = row[0]

        sql = "SELECT name, is_dir, size FROM entries WHERE parent_id = ?"
        params = [parent_id]

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
        rows = cursor.fetchall()

        # Build path separator safely
        sep = "\\" if "\\" in parent_path else "/"
        
        needs_date_filter = min_mtime > 0 or max_mtime > 0
        out = []
        for r_name, r_is_dir, r_size in rows:
            path = parent_path + sep + r_name if not parent_path.endswith(sep) else parent_path + r_name
            st = self._stat(path)
            
            if needs_date_filter and not r_is_dir:
                if min_mtime > 0 and st[0] < min_mtime: continue
                if max_mtime > 0 and st[0] > max_mtime: continue

            out.append({
                "path": path,
                "parent": parent_path,
                "name": r_name,
                "is_dir": r_is_dir,
                "size": st[2] if st[2] else r_size,
                "mtime": st[0],
                "ctime": st[1]
            })
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
        sql = """
        SELECT d.path as parent, e.name, e.is_dir, e.size 
        FROM entries e
        JOIN directories d ON e.parent_id = d.id
        WHERE 1=1
        """
        params = []

        for term in terms:
            sql += f" AND e.name {op} ?"
            params.append(f"*{term}*" if case_sensitive else f"%{term}%")

        if file_types:
            exts = []
            for ft in file_types:
                exts.extend(self._get_exts_for_type(ft))
            if exts:
                sql += (
                    " AND (e.is_dir = 1 OR ("
                    + " OR ".join(["e.name LIKE ?" for _ in exts])
                    + "))"
                )
                params.extend([f"%.{e}" for e in exts])

        if parent_prefix:
            p = parent_prefix.replace("\\", "/").rstrip("/")
            sql += " AND (replace(d.path,'\\','/') = ? OR replace(d.path,'\\','/') LIKE ?)"
            params.append(p)
            params.append(f"{p}/%")

        sql += " LIMIT 2000"
        cursor = self.conn.execute(sql, params)
        rows = cursor.fetchall()

        needs_date_filter = min_mtime > 0 or max_mtime > 0
        out = []
        for r_parent, r_name, r_is_dir, r_size in rows:
            sep = "\\" if "\\" in r_parent else "/"
            path = r_parent + sep + r_name if not r_parent.endswith(sep) else r_parent + r_name
            
            st = self._stat(path)
            if needs_date_filter and not r_is_dir:
                if min_mtime > 0 and st[0] < min_mtime: continue
                if max_mtime > 0 and st[0] > max_mtime: continue

            out.append({
                "path": path,
                "parent": r_parent,
                "name": r_name,
                "is_dir": r_is_dir,
                "size": st[2] if st[2] else r_size,
                "mtime": st[0],
                "ctime": st[1]
            })
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
            """
            SELECT COUNT(*) 
            FROM entries e
            JOIN directories d ON e.parent_id = d.id
            WHERE d.path = ? OR d.path LIKE ? || '/%' OR d.path LIKE ? || '\\%'
            """,
            (root_path, root_path, root_path),
        )
        return cursor.fetchone()[0]

    def close(self):
        self.conn.close()
