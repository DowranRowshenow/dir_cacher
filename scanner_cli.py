import os
import sys
import sqlite3
import time

def scan(db_path, scan_dirs):
    conn = sqlite3.connect(db_path, timeout=30000)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA cache_size = -32768")
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            path TEXT PRIMARY KEY,
            parent TEXT,
            name TEXT,
            is_dir BOOLEAN,
            size INTEGER,
            mtime REAL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parent ON entries(parent)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON entries(name)")

    total = 0
    batch = []
    
    for root_dir in scan_dirs:
        print(f"START:{root_dir}", flush=True)
        stack = [root_dir]
        
        while stack:
            curr = stack.pop()
            try:
                with os.scandir(curr) as it:
                    for entry in it:
                        try:
                            is_dir = entry.is_dir(follow_symlinks=False)
                            stat = entry.stat(follow_symlinks=False)
                            
                            batch.append((
                                entry.path,
                                curr,
                                entry.name,
                                is_dir,
                                stat.st_size,
                                stat.st_mtime
                            ))
                            total += 1
                            
                            if is_dir:
                                stack.append(entry.path)
                                
                            if len(batch) >= 1000:
                                with conn:
                                    conn.executemany("""
                                        INSERT INTO entries (path, parent, name, is_dir, size, mtime)
                                        VALUES (?, ?, ?, ?, ?, ?)
                                        ON CONFLICT(path) DO UPDATE SET
                                            size=excluded.size,
                                            mtime=excluded.mtime
                                    """, batch)
                                batch = []
                                print(f"PROGRESS:{total}", flush=True)
                                
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue
                
    if batch:
        with conn:
            conn.executemany("""
                INSERT INTO entries (path, parent, name, is_dir, size, mtime)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    size=excluded.size,
                    mtime=excluded.mtime
            """, batch)
            
    conn.close()
    print(f"DONE:{total}", flush=True)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    scan(sys.argv[1], sys.argv[2:])
