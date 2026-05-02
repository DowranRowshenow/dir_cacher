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
        self.create_tables()

    def create_tables(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    path TEXT PRIMARY KEY,
                    parent TEXT,
                    name TEXT,
                    is_dir BOOLEAN,
                    size INTEGER,
                    mtime REAL
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_parent ON entries(parent)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON entries(name)")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_status (
                    root_path TEXT PRIMARY KEY,
                    last_scan REAL
                )
            """)

    def upsert_entries(self, entries: List[Dict]):
        with self.conn:
            self.conn.executemany("""
                INSERT INTO entries (path, parent, name, is_dir, size, mtime)
                VALUES (:path, :parent, :name, :is_dir, :size, :mtime)
                ON CONFLICT(path) DO UPDATE SET
                    size=excluded.size,
                    mtime=excluded.mtime
            """, entries)

    def replace_children(self, parent_path: str, entries: List[Dict]):
        with self.conn:
            self.conn.execute("DELETE FROM entries WHERE parent = ?", (parent_path,))
            if entries:
                self.conn.executemany("""
                    INSERT INTO entries (path, parent, name, is_dir, size, mtime)
                    VALUES (:path, :parent, :name, :is_dir, :size, :mtime)
                """, entries)

    def get_children(self, parent_path: str) -> List[Dict]:
        cursor = self.conn.execute(
            "SELECT path, parent, name, is_dir, size, mtime FROM entries WHERE parent = ? ORDER BY is_dir DESC, name ASC LIMIT 1000",
            (parent_path,)
        )
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def update_scan_status(self, root_path: str, timestamp: float):
        with self.conn:
            self.conn.execute("""
                INSERT INTO scan_status (root_path, last_scan)
                VALUES (?, ?)
                ON CONFLICT(root_path) DO UPDATE SET last_scan=excluded.last_scan
            """, (root_path, timestamp))

    def get_scan_status(self, root_path: str) -> Optional[float]:
        cursor = self.conn.execute("SELECT last_scan FROM scan_status WHERE root_path = ?", (root_path,))
        row = cursor.fetchone()
        return row[0] if row else None

    def search(self, query: str, parent_prefix: Optional[str] = None) -> List[Dict]:
        terms = [t.strip() for t in query.split("&") if t.strip()]
        if not terms:
            return []

        sql = "SELECT path, parent, name, is_dir, size, mtime FROM entries WHERE 1=1"
        params = []
        for term in terms:
            sql += " AND name LIKE ?"
            params.append(f"%{term}%")
        
        if parent_prefix:
            # Normalize to forward slashes to handle both Qt (/) and Win32 (\) paths
            p = parent_prefix.replace("\\", "/").rstrip("/")
            sql += " AND (replace(path, '\\', '/') = ? OR replace(path, '\\', '/') LIKE ?)"
            params.append(p)
            params.append(f"{p}/%")

        sql += " LIMIT 1000"
        
        cursor = self.conn.execute(sql, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self):
        self.conn.close()
