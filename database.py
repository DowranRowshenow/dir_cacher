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

    def upsert_entries(self, entries: List[Dict]):
        with self.conn:
            self.conn.executemany("""
                INSERT INTO entries (path, parent, name, is_dir, size, mtime)
                VALUES (:path, :parent, :name, :is_dir, :size, :mtime)
                ON CONFLICT(path) DO UPDATE SET
                    size=excluded.size,
                    mtime=excluded.mtime
            """, entries)

    def get_children(self, parent_path: str) -> List[Dict]:
        cursor = self.conn.execute(
            "SELECT path, parent, name, is_dir, size, mtime FROM entries WHERE parent = ? ORDER BY is_dir DESC, name ASC LIMIT 1000",
            (parent_path,)
        )
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def search(self, query: str, parent_prefix: Optional[str] = None) -> List[Dict]:
        sql = "SELECT path, parent, name, is_dir, size, mtime FROM entries WHERE name LIKE ?"
        params = [f"%{query}%"]
        
        if parent_prefix:
            # Scoped search: match items inside parent_prefix or the prefix itself
            # Normalize to avoid slash mismatches
            p = parent_prefix.replace("\\", "/").rstrip("/")
            sql += " AND (path = ? OR path LIKE ?)"
            params.append(parent_prefix)
            params.append(f"{p}/%")

        sql += " LIMIT 1000"
        
        cursor = self.conn.execute(sql, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self):
        self.conn.close()
