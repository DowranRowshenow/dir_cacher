use std::ffi::{CStr, CString};
use std::fs;
use std::os::raw::c_char;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::SystemTime;

#[no_mangle]
pub extern "C" fn create_cancel_flag() -> *mut AtomicBool {
    Box::into_raw(Box::new(AtomicBool::new(false)))
}

#[no_mangle]
pub extern "C" fn cancel_scan(flag: *mut AtomicBool) {
    if !flag.is_null() {
        unsafe { (*flag).store(true, Ordering::Relaxed) };
    }
}

#[no_mangle]
pub extern "C" fn free_cancel_flag(flag: *mut AtomicBool) {
    if !flag.is_null() {
        unsafe { drop(Box::from_raw(flag)) };
    }
}

pub type EntryCallback = extern "C" fn(
    path: *const c_char,
    parent: *const c_char,
    name: *const c_char,
    is_dir: i32,
    size: i64,
    mtime: f64,
);

#[no_mangle]
pub extern "C" fn scan_directory(
    root_path: *const c_char,
    cancel_flag: *mut AtomicBool,
    callback: Option<EntryCallback>,
) -> i64 {
    let root = match unsafe { CStr::from_ptr(root_path) }.to_str() {
        Ok(s) => s.to_owned(),
        Err(_) => return -1,
    };

    let cancel = if cancel_flag.is_null() {
        return -1;
    } else {
        unsafe { &*cancel_flag }
    };

    let cb = match callback {
        Some(c) => c,
        None => return -1,
    };

    let mut total = 0;
    let mut stack = vec![root];

    while let Some(curr) = stack.pop() {
        if cancel.load(Ordering::Relaxed) {
            break;
        }

        let read_dir = match fs::read_dir(&curr) {
            Ok(rd) => rd,
            Err(_) => continue,
        };

        for entry_res in read_dir {
            if cancel.load(Ordering::Relaxed) {
                break;
            }
            let entry = match entry_res {
                Ok(e) => e,
                Err(_) => continue,
            };

            let path_buf = entry.path();
            let path_str = path_buf.to_string_lossy();
            let parent_str = path_buf
                .parent()
                .map(|p| p.to_string_lossy())
                .unwrap_or_default();
            let name_str = entry.file_name();
            let name_str_lossy = name_str.to_string_lossy();

            let metadata = match entry.metadata() {
                Ok(m) => m,
                Err(_) => continue,
            };

            let is_dir = metadata.is_dir() as i32;
            let size = if is_dir == 1 { 0 } else { metadata.len() as i64 };
            let mtime = metadata
                .modified()
                .unwrap_or(SystemTime::UNIX_EPOCH)
                .duration_since(SystemTime::UNIX_EPOCH)
                .map(|d| d.as_secs_f64())
                .unwrap_or(0.0);

            if is_dir == 1 {
                stack.push(path_str.to_string());
            }

            // Convert to CString
            let c_path = match CString::new(path_str.as_ref()) {
                Ok(c) => c,
                Err(_) => continue,
            };
            let c_parent = match CString::new(parent_str.as_ref()) {
                Ok(c) => c,
                Err(_) => continue,
            };
            let c_name = match CString::new(name_str_lossy.as_ref()) {
                Ok(c) => c,
                Err(_) => continue,
            };

            cb(c_path.as_ptr(), c_parent.as_ptr(), c_name.as_ptr(), is_dir, size, mtime);
            total += 1;
        }
    }

    total
}
