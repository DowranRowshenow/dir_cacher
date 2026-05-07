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
                    mtime  REAL NOT NULL DEFAULT 0,
                    ctime  REAL NOT NULL DEFAULT 0,
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
            
            # Check and add last_seen column if missing
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA table_info(entries)")
            cols = {row[1] for row in cursor.fetchall()}
            if "last_seen" not in cols:
                try:
                    self.conn.execute("ALTER TABLE entries ADD COLUMN last_seen REAL NOT NULL DEFAULT 0")
                except Exception:
                    pass

    def _migrate(self):
        """Migrate legacy schema (flat path/parent) to relation schema (directories/entries)."""
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(entries)")
        cols = {row[1] for row in cursor.fetchall()}

        if "path" in cols:
            # Old schema detected — perform data migration
            try:
                with self.conn:
                    # 1. Rename old table
                    self.conn.execute("ALTER TABLE entries RENAME TO old_entries")
                    
                    # 2. Create fresh entries table
                    self.conn.execute(
                        """
                        CREATE TABLE entries (
                            parent_id INTEGER NOT NULL,
                            name   TEXT NOT NULL,
                            is_dir INTEGER NOT NULL DEFAULT 0,
                            size   INTEGER NOT NULL DEFAULT 0,
                            mtime  REAL NOT NULL DEFAULT 0,
                            ctime  REAL NOT NULL DEFAULT 0,
                            PRIMARY KEY (parent_id, name)
                        ) WITHOUT ROWID
                        """
                    )
                    
                    # 3. Extract unique parent paths
                    self.conn.execute(
                        "INSERT OR IGNORE INTO directories (path) SELECT DISTINCT parent FROM old_entries WHERE parent != ''"
                    )
                    
                    # 4. Insert mapped data
                    self.conn.execute(
                        """
                        INSERT OR IGNORE INTO entries (parent_id, name, is_dir, size, mtime, ctime)
                        SELECT d.id, o.name, o.is_dir, o.size, 0, 0
                        FROM old_entries o
                        JOIN directories d ON d.path = o.parent
                        """
                    )
                    
                    # 5. Drop old table
                    self.conn.execute("DROP TABLE old_entries")
            except Exception as e:
                print(f"Migration error (path): {e}")

        elif "mtime" not in cols:
            # Intermediate schema (parent_id but no mtime) — Rebuild because WITHOUT ROWID doesn't support ALTER ADD COLUMN
            try:
                with self.conn:
                    self.conn.execute("ALTER TABLE entries RENAME TO entries_old")
                    self.conn.execute(
                        """
                        CREATE TABLE entries (
                            parent_id INTEGER NOT NULL,
                            name   TEXT NOT NULL,
                            is_dir INTEGER NOT NULL DEFAULT 0,
                            size   INTEGER NOT NULL DEFAULT 0,
                            mtime  REAL NOT NULL DEFAULT 0,
                            ctime  REAL NOT NULL DEFAULT 0,
                            PRIMARY KEY (parent_id, name)
                        ) WITHOUT ROWID
                        """
                    )
                    self.conn.execute(
                        """
                        INSERT INTO entries (parent_id, name, is_dir, size, mtime, ctime)
                        SELECT parent_id, name, is_dir, size, 0, 0 FROM entries_old
                        """
                    )
                    self.conn.execute("DROP TABLE entries_old")
            except Exception as e:
                print(f"Migration error (mtime): {e}")

        # Reclaim freed pages immediately
        try:
            self.conn.execute("VACUUM")
        except:
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
                    items.append((pid, e["name"], e["is_dir"], e["size"], e.get("mtime", 0), e.get("ctime", 0), e.get("last_seen", 0)))
            
            self.conn.executemany(
                """
                INSERT INTO entries (parent_id, name, is_dir, size, mtime, ctime, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(parent_id, name) DO UPDATE SET
                    is_dir = excluded.is_dir,
                    size   = excluded.size,
                    mtime  = excluded.mtime,
                    ctime  = excluded.ctime,
                    last_seen = excluded.last_seen
                """,
                items,
            )

    def cleanup_missing(self, paths: List[str], scan_time: float, recursive: bool):
        with self.conn:
            for p in paths:
                if recursive:
                    self.conn.execute(
                        """
                        DELETE FROM entries 
                        WHERE last_seen < ? 
                          AND parent_id IN (
                            SELECT id FROM directories 
                            WHERE path = ? OR path GLOB ? OR path GLOB ?
                          )
                        """,
                        (scan_time, p, p + "/*", p + "\\*")
                    )
                else:
                    self.conn.execute(
                        """
                        DELETE FROM entries
                        WHERE last_seen < ?
                          AND parent_id = (SELECT id FROM directories WHERE path = ?)
                        """,
                        (scan_time, p)
                    )
            
            # Delete orphaned directories
            self.conn.execute(
                "DELETE FROM directories WHERE id NOT IN (SELECT DISTINCT parent_id FROM entries)"
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
        limit: int = 1000,
        offset: int = 0,
    ) -> List[Dict]:
        cursor = self.conn.execute("SELECT id FROM directories WHERE path = ?", (parent_path,))
        row = cursor.fetchone()
        if not row:
            return []
        parent_id = row[0]

        sql = "SELECT name, is_dir, size, mtime, ctime FROM entries WHERE parent_id = ?"
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

        sql += " ORDER BY is_dir DESC, name ASC"
        if limit > 0:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
        cursor = self.conn.execute(sql, params)
        rows = cursor.fetchall()

        # Build path separator safely
        sep = "\\" if "\\" in parent_path else "/"
        
        needs_date_filter = min_mtime > 0 or max_mtime > 0
        out = []
        for r_name, r_is_dir, r_size, r_mtime, r_ctime in rows:
            path = parent_path + sep + r_name if not parent_path.endswith(sep) else parent_path + r_name
            
            if needs_date_filter and not r_is_dir:
                if min_mtime > 0 and r_mtime < min_mtime: continue
                if max_mtime > 0 and r_mtime > max_mtime: continue
            
            out.append({
                "path": path,
                "parent": parent_path,
                "name": r_name,
                "is_dir": r_is_dir,
                "size": r_size,
                "mtime": r_mtime,
                "ctime": r_ctime
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
        delimiter: str = "&",
        wildcard_char: str = "*",
        limit: int = 1000,
        offset: int = 0,
    ) -> List[Dict]:
        terms = [t.strip() for t in query.split(delimiter) if t.strip()]
        if not terms and not file_types and min_mtime == 0:
            return []

        op = "GLOB" if case_sensitive else "LIKE"
        sql = """
        SELECT d.path as parent, e.name, e.is_dir, e.size, e.mtime, e.ctime 
        FROM entries e
        JOIN directories d ON e.parent_id = d.id
        WHERE 1=1
        """
        params = []

        for term in terms:
            sql += f" AND e.name {op} ?"
            if wildcard_char and wildcard_char in term:
                if case_sensitive:
                    params.append(term.replace(wildcard_char, "*"))
                else:
                    params.append(term.replace(wildcard_char, "%"))
            else:
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

        if limit > 0:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
        cursor = self.conn.execute(sql, params)
        rows = cursor.fetchall()

        needs_date_filter = min_mtime > 0 or max_mtime > 0
        out = []
        for r_parent, r_name, r_is_dir, r_size, r_mtime, r_ctime in rows:
            sep = "\\" if "\\" in r_parent else "/"
            path = r_parent + sep + r_name if not r_parent.endswith(sep) else r_parent + r_name
            
            if needs_date_filter and not r_is_dir:
                if min_mtime > 0 and r_mtime < min_mtime: continue
                if max_mtime > 0 and r_mtime > max_mtime: continue

            out.append({
                "path": path,
                "parent": r_parent,
                "name": r_name,
                "is_dir": r_is_dir,
                "size": r_size,
                "mtime": r_mtime,
                "ctime": r_ctime
            })
        return out

    def raw_sql_search(self, sql: str) -> List[Dict]:
        """
        Executes a raw SELECT query and tries to map columns to file entry format.
        Expected columns in some form: name, path, is_dir, size.
        """
        try:
            cursor = self.conn.execute(sql)
            columns = [column[0].lower() for column in cursor.description]
            rows = cursor.fetchall()
            
            out = []
            for row in rows:
                data = dict(zip(columns, row))
                # Heuristic mapping
                name = data.get("name", "Unknown")
                path = data.get("path", name)
                is_dir = data.get("is_dir", 0)
                size = data.get("size", 0)
                
                # Try to get mtime/ctime if available in row or via stat
                mtime = data.get("mtime", 0)
                ctime = data.get("ctime", 0)
                if mtime == 0:
                    st = self._stat(path)
                    mtime, ctime = st[0], st[1]
                
                out.append({
                    "path": path,
                    "name": name,
                    "is_dir": bool(is_dir),
                    "size": size,
                    "mtime": mtime,
                    "ctime": ctime
                })
            return out
        except Exception as e:
            # Return error as a pseudo-entry or just empty
            return [{"name": f"SQL Error: {str(e)}", "path": "", "is_dir": 0, "size": 0, "mtime": 0, "ctime": 0}]

    # ── Helpers ───────────────────────────────────────────
    def _stat(self, path: str):
        """Returns (mtime, ctime, size) from disk, or (0, 0, 0) on error."""
        try:
            s = os.stat(path)
            return s.st_mtime, s.st_ctime, s.st_size
        except OSError:
            return 0.0, 0.0, 0

    def delete_entry(self, path: str):
        with self.conn:
            # First, check if it's a directory in our index
            cursor = self.conn.execute("SELECT id FROM directories WHERE path = ?", (path,))
            row = cursor.fetchone()
            if row:
                dir_id = row[0]
                # Delete all child entries
                self.conn.execute("DELETE FROM entries WHERE parent_id = ?", (dir_id,))
                # Delete the directory itself
                self.conn.execute("DELETE FROM directories WHERE id = ?", (dir_id,))
            
            # Delete from entries table (where it's a child of some other dir)
            parent_path = os.path.dirname(path)
            cursor = self.conn.execute("SELECT id FROM directories WHERE path = ?", (parent_path,))
            row = cursor.fetchone()
            if row:
                pid = row[0]
                self.conn.execute("DELETE FROM entries WHERE parent_id = ? AND name = ?", (pid, os.path.basename(path)))

    def rename_entry(self, old_path: str, new_path: str):
        with self.conn:
            old_name = os.path.basename(old_path)
            new_name = os.path.basename(new_path)
            parent_path = os.path.dirname(old_path)
            
            cursor = self.conn.execute("SELECT id FROM directories WHERE path = ?", (parent_path,))
            row = cursor.fetchone()
            if row:
                pid = row[0]
                self.conn.execute("UPDATE entries SET name = ? WHERE parent_id = ? AND name = ?", (new_name, pid, old_name))
            
            # If it's a directory, update its own path and all child paths (complex, but let's try)
            cursor = self.conn.execute("SELECT id FROM directories WHERE path = ?", (old_path,))
            row = cursor.fetchone()
            if row:
                dir_id = row[0]
                self.conn.execute("UPDATE directories SET path = ? WHERE id = ?", (new_path, dir_id))
                # Note: children entries don't store full path, just parent_id, so they stay linked! Correct!

    def _get_exts_for_type(self, file_type: str) -> List[str]:
        mapping = {
            "Excel":       ["xlsx", "xls", "csv", "xlsm"],
            "PDF":         ["pdf"],
            "Word":        ["docx", "doc", "rtf"],
            "Drawings":    ["dwg", "dxf"],
            "Images":      ["png", "jpg", "jpeg", "gif", "bmp", "svg", "webp"],
            "Archives":    ["zip", "rar", "7z", "tar", "gz"],
            "Executables": ["exe", "msi", "bat", "cmd"],
            "Videos":      ["mp4", "mkv", "avi", "mov", "wmv"],
            "Music":       ["mp3", "wav", "flac", "aac", "ogg"],
            "Text Files":  ["txt", "md", "log", "ini", "cfg", "conf", "py", "js", "html", "css", "cpp", "c", "h", "java", "cs", "ts", "json", "xml", "yaml", "sh", "ps1"],
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
