# ✅ MASTER PROMPT FOR AI AGENTS

## Project: High‑Performance Network Directory Indexer & Explorer

### 🎯 Project Goal

Build a **modern, high‑performance directory indexing and file explorer application** using:

*   **Python** for GUI and orchestration
*   **Rust** for high‑speed directory scanning & indexing
*   **SQLite** for shared cache (local or network)
*   **Fluent UI–inspired design** (Windows‑style modern UX)

Primary use case: **network directory indexing & shared cache usage** without UI freezing.

***

## 🧱 Architecture (DO NOT DEVIATE)

    GUI Layer (Python)
     ├─ Fluent-style user interface
     ├─ Table-based file explorer
     ├─ Filter / sort / search
     ├─ Progress + control
     └─ Reads cached data

    Core Backend (Rust)
     ├─ Directory scanning
     ├─ Metadata extraction
     ├─ Parallel traversal
     ├─ SQLite writes
     └─ Cache existence checks

✅ **Rust NEVER touches UI**
✅ **Python NEVER scans directories**
✅ **All heavy IO = Rust**
✅ **All UI = Python**

***

## 🖥 UI REQUIREMENTS (Fluent UI Style)

### Framework

*   Python GUI framework capable of Fluent‑like UI (PySide6 + custom styling)
*   Clean spacing, icons, smooth interactions
*   Non‑blocking UX at all times

### Main Layout

*   Left: Explorer tree / directory list
*   Center: **Table‑based explorer**
*   Top: Toolbar & search
*   Bottom: Scan progress bar + status

***

## ⚙️ SETTINGS PANEL (MANDATORY)

### 1. Directories to Scan

*   Allow **multiple directories**
*   If **one directory only** → open directly into it
*   If **multiple directories** → show them as root explorer entries
*   Editable list (add/remove)

### 2. Cache Directory

*   User specifies **cache database location**
*   Must support **network paths**
*   All machines can **read/write same cache**
*   SQLite WAL mode enabled

Purpose:

> Centralized indexing → faster access for everyone

***

## 📁 FILE EXPLORER (TABLE VIEW)

### Columns (sortable + filterable)

| Column   | Description                |
| -------- | -------------------------- |
| Name     | File or directory name     |
| Type     | File extension or “Folder” |
| Size     | Human‑readable             |
| Modified | Last modified time         |
| Path     | Optional                   |

### Features

*   Icons for **file types and folders**
*   Sort by any column
*   Filter by:
    *   Date
    *   Size range
    *   File type
    *   File vs folder
*   Context menu:
    *   Open
    *   Reveal in OS
    *   Copy path

***

## 🔍 SEARCH SYSTEM (ADVANCED)

### Search Bar

*   Highlight matching items in Explorer
*   SQLite‑based (NO filesystem hits)

### Supported

*   Wildcards (`*`, `?`)
*   File type filters (`*.pdf`)
*   Size filters (`>10MB`)
*   Folder‑only / file‑only
*   Case‑insensitive

✅ Search only cached data  
✅ Results appear instantly

***

## 🔄 SCANNING BEHAVIOR (VERY IMPORTANT)

### Automatic Scan Rules

*   When a directory is opened:
    *   ✅ Scan **ONLY current directory (shallow)**
    *   ❌ No recursive deep scan
*   Scan happens **only if cache does NOT exist**

### Manual Scan Button

*   Scans **deep tree recursively**
*   Starts from **currently selected directory**
*   Uses **Rust + threads**
*   Shows:
    *   Progress bar
    *   Current directory being scanned
    *   Cancel button (must stop cleanly)

### Performance Rules

*   UI must NEVER freeze
*   Scans must be cancellable
*   Rust threads must handle traversal
*   Python UI receives progress via signals

***

## ⚡ RUST BACKEND REQUIREMENTS

### Rust Responsibilities

*   Directory traversal (parallel)
*   Metadata extraction
*   SQLite writes
*   Incremental cache checks

### Technical

*   Use `walkdir` + `rayon`
*   Use SQLite transactions
*   Enable:
    ```sql
    PRAGMA journal_mode = WAL;
    PRAGMA synchronous = NORMAL;
    ```

### Expose to Python via:

*   `PyO3`
*   Compiled as native module
*   No subprocess usage

***

## 📦 DATABASE REQUIREMENTS

### SQLite Schema

*   Entries:
    *   path (PRIMARY KEY)
    *   parent
    *   name
    *   is\_dir
    *   size
    *   mtime
*   Indexed for:
    *   Parent lookups
    *   Sorting
*   Full‑text search (FTS5)

### Characteristics

*   Shared across network
*   Read‑heavy optimized
*   Safe concurrent access

***

## 🧵 CONCURRENCY & UX RULES (STRICT)

❌ No blocking calls on UI thread  
❌ No recursive UI loads  
✅ All scans in background threads  
✅ Lazy loading in explorer  
✅ Cancel safe scan

***

## ✅ DELIVERY EXPECTATIONS FOR AGENTS

Agents should deliver:

1.  **Python GUI code (modular)**
2.  **Rust backend with PyO3**
3.  **Database schema**
4.  **Clear separation of concerns**
5.  **Run instructions**
6.  **Basic styling (Fluent‑like)**

No placeholder implementations.  
No pseudo‑code in final output.  
Focus on correctness + performance.

***

## 🚫 DO NOT

*   Scan filesystem from Python
*   Block UI thread
*   Preload entire trees
*   Ignore network cache use case

***

### ✅ Success Criteria

When the app starts:

*   UI loads instantly
*   Directories appear based on settings
*   Cached data shows immediately
*   Manual scan is fast, controllable, and silent to UI
