# Distributed SQLite File Indexing System — AI Agent Instructions

## 🎯 Objective

Design and maintain a **collaborative file indexing system** where:
- Multiple users scan file systems
- All contributions are combined into a shared index
- Searches are fast and local
- No full rescanning is required per user

---

## 🧠 Core Principles

1. **No Shared Live Writes**
   - SQLite must NOT be written by multiple users over network
   - Avoid concurrent writes to a single `.db` file

2. **Local-First Architecture**
   - Each user:
     - Scans locally
     - Writes to local database
     - Performs search on local copy

3. **Distributed Contribution**
   - Users contribute scan results (deltas)
   - Contributions are merged centrally

4. **Single Source of Truth**
   - `master.db` acts as global index
   - Distributed to all users

---

## 🏗️ System Architecture

```

User A ─┐
User B ─┼──→ updates → merge → master.db → sync → local.db (per user)
User C ─┘

````

---

## 📦 Database Schema

### directories
```sql
CREATE TABLE directories (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL
)
````

### entries

```sql
CREATE TABLE entries (
    parent_id INTEGER NOT NULL,
    name   TEXT NOT NULL,
    is_dir INTEGER NOT NULL DEFAULT 0,
    size   INTEGER NOT NULL DEFAULT 0,
    mtime  REAL NOT NULL DEFAULT 0,
    ctime  REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (parent_id, name)
) WITHOUT ROWID
```

### scan\_status

```sql
CREATE TABLE scan_status (
    root_path TEXT PRIMARY KEY,
    last_scan REAL
) WITHOUT ROWID
```

### (Optional) changes log

```sql
CREATE TABLE changes (
    parent TEXT,
    name TEXT,
    is_dir INTEGER,
    size INTEGER,
    mtime REAL,
    ctime REAL,
    ts REAL
)
```

***

## 🔄 Data Flow

### 1. Local Scanning

*   Each client scans filesystem
*   Writes to `local.db`
*   Optionally logs changes in `changes` table

***

### 2. Export Updates

*   Export incremental updates to file:

<!---->

    network/updates/user_X_timestamp.db

*   Always write via:
    1.  temp file
    2.  atomic rename

***

### 3. Merge Process

Only ONE process must merge at a time.

#### Merge steps:

1.  Lock merge operation
2.  Read update files
3.  Insert into `master.db`:

```sql
INSERT INTO entries (...)
ON CONFLICT(parent_id, name) DO UPDATE ...
```

4.  Delete processed updates
5.  Release lock

***

## 🔒 Concurrency Rules

*   Only one writer allowed for `master.db`
*   Multiple readers allowed
*   Never allow multiple merge processes

***

## ⚡ Performance Strategy

1.  Use WAL mode:

```sql
PRAGMA journal_mode = WAL;
```

2.  Indexing:

```sql
CREATE INDEX idx_entries_name ON entries(name);
CREATE INDEX idx_entries_parent_dir ON entries(parent_id, is_dir, name);
```

3.  Limit queries:

```sql
LIMIT 2000
```

4.  Cache query results when needed

***

## 🔍 Search Behavior

*   Support wildcard / multi-term search:

<!---->

    inv*&15&.pdf

*   Split into tokens:

<!---->

    ["inv", "15", ".pdf"]

*   Query:

```sql
WHERE name LIKE '%inv%'
  AND name LIKE '%15%'
  AND name LIKE '%.pdf%'
```

***

## 🚀 Optional: FTS5 (Full-Text Search)

```sql
CREATE VIRTUAL TABLE entries_fts USING fts5(name);
```

*   Improves search speed significantly
*   Increases DB size (\~30–80%)

***

## 🔁 Sync Strategy

*   Maintain version file:

<!---->

    master.version

*   On client launch:

<!---->

    IF server_version > local_version:
        download master.db
    ELSE:
        use local.db

*   Do NOT reload DB every launch unnecessarily

***

## ✅ Fail-Safe Rules

1.  Always use transactions:

```python
with conn:
```

2.  Use atomic file writes:

<!---->

    write temp.db → rename → final.db

3.  Skip corrupted update files during merge

4.  Use WAL mode for crash recovery

***

## ❌ Forbidden Actions

*   Do NOT:
    *   Write to shared SQLite over network
    *   Run multiple merge processes
    *   Load entire DB into memory unnecessarily
    *   Duplicate full paths repeatedly

***

## ✅ Recommended Behavior for Agent

*   Treat database as authoritative index
*   Prefer incremental updates over full scans
*   Optimize for read performance
*   Minimize memory footprint
*   Avoid unsafe concurrency patterns

***

## 🧾 One-Line Summary

> Use **distributed scanning + single merge + local querying** to achieve fast, scalable, and safe file indexing.
