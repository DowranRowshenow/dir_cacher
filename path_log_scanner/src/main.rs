use rusqlite::{Connection, params};
use std::env;
use std::path::Path;
use std::time::SystemTime;
use walkdir::WalkDir;

struct Entry {
    path: String,
    parent: String,
    name: String,
    is_dir: bool,
    size: u64,
    mtime: f64,
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!("Usage: pathlog_scanner <db_path> <scan_dir> [scan_dir2 ...]");
        std::process::exit(1);
    }

    let db_path = &args[1];
    let scan_dirs = &args[2..];

    let conn = Connection::open(db_path).expect("Failed to open database");

    // Enable WAL mode for fast concurrent writes
    conn.execute_batch("
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;
        PRAGMA cache_size = -32768;
        PRAGMA temp_store = MEMORY;
        CREATE TABLE IF NOT EXISTS entries (
            path TEXT PRIMARY KEY,
            parent TEXT,
            name TEXT,
            is_dir BOOLEAN,
            size INTEGER,
            mtime REAL
        );
        CREATE INDEX IF NOT EXISTS idx_parent ON entries(parent);
        CREATE INDEX IF NOT EXISTS idx_name ON entries(name);
    ").expect("Failed to init DB");

    let mut batch: Vec<Entry> = Vec::with_capacity(500);
    let mut total: u64 = 0;

    for scan_dir in scan_dirs {
        // Print start marker
        println!("START:{}", scan_dir);

        for entry in WalkDir::new(scan_dir)
            .follow_links(false)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            let path = entry.path();
            let parent = path.parent()
                .map(|p| p.to_string_lossy().into_owned())
                .unwrap_or_default();
            let name = path.file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default();

            // Skip root itself
            if name.is_empty() {
                continue;
            }

            let meta = match entry.metadata() {
                Ok(m) => m,
                Err(_) => continue,
            };

            let mtime = meta.modified()
                .ok()
                .and_then(|t| t.duration_since(SystemTime::UNIX_EPOCH).ok())
                .map(|d| d.as_secs_f64())
                .unwrap_or(0.0);

            let size = if meta.is_file() { meta.len() } else { 0 };
            let is_dir = meta.is_dir();

            batch.push(Entry {
                path: path.to_string_lossy().into_owned(),
                parent,
                name,
                is_dir,
                size,
                mtime,
            });
            total += 1;

            if batch.len() >= 500 {
                flush_batch(&conn, &mut batch);
                println!("PROGRESS:{}", total);
            }
        }
    }

    if !batch.is_empty() {
        flush_batch(&conn, &mut batch);
    }

    println!("DONE:{}", total);
}

fn flush_batch(conn: &Connection, batch: &mut Vec<Entry>) {
    let tx = conn.unchecked_transaction().expect("Transaction failed");
    {
        let mut stmt = conn.prepare_cached("
            INSERT INTO entries (path, parent, name, is_dir, size, mtime)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6)
            ON CONFLICT(path) DO UPDATE SET
                size = excluded.size,
                mtime = excluded.mtime
        ").expect("Prepare failed");

        for e in batch.iter() {
            let _ = stmt.execute(params![
                e.path, e.parent, e.name,
                e.is_dir as i32, e.size as i64, e.mtime
            ]);
        }
    }
    tx.commit().expect("Commit failed");
    batch.clear();
}
