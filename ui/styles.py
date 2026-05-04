STYLESHEET = """
* {
    font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
    font-size: 14px;
    color: #1a1a1a;
}

QMainWindow {
    background-color: #f3f3f3;
}

/* ─── Sidebar ─────────────────────────────── */
#sidebar {
    background-color: #f3f3f3;
    border-right: 1px solid #e0e0e0;
}

#app_title_label {
    font-size: 13px;
    font-weight: 600;
    color: #1a1a1a;
    padding: 0px 12px;
}

/* Nav item buttons */
#nav_btn {
    text-align: left;
    padding: 8px 12px 8px 12px;
    border: none;
    border-radius: 6px;
    margin: 1px 4px;
    background-color: transparent;
    font-size: 13px;
    color: #1a1a1a;
}

#nav_btn:hover {
    background-color: rgba(0, 0, 0, 0.05);
}

#nav_btn_active {
    text-align: left;
    padding: 8px 12px 8px 12px;
    border: none;
    border-radius: 6px;
    margin: 1px 4px;
    background-color: rgba(0, 120, 212, 0.1);
    font-size: 13px;
    color: #1a1a1a;
    font-weight: 600;
}

#nav_btn_active:hover {
    background-color: rgba(0, 120, 212, 0.15);
}

#nav_section_label {
    font-size: 11px;
    font-weight: 600;
    color: #6e6e6e;
    padding: 6px 16px 2px 16px;
    letter-spacing: 0.5px;
}

/* ─── Main Content ─────────────────────────── */
#content_area {
    background-color: #ffffff;
}

#page_title {
    font-size: 28px;
    font-weight: 600;
    color: #1a1a1a;
    padding-bottom: 4px;
}

#page_subtitle {
    font-size: 13px;
    color: #6e6e6e;
}

/* ─── Info Banner ──────────────────────────── */
#info_banner {
    background-color: #eff6fc;
    border: 1px solid #cce4f7;
    border-radius: 8px;
    padding: 10px 16px;
}

#info_banner_text {
    font-size: 13px;
    color: #1a1a1a;
}

/* ─── Card / Setting Row ───────────────────── */
#card {
    background-color: #fafafa;
    border: 1px solid #e5e5e5;
    border-radius: 8px;
}

#card_header_label {
    font-size: 13px;
    font-weight: 600;
    color: #1a1a1a;
    padding: 14px 16px 0px 16px;
}

#setting_row {
    background-color: transparent;
    border-bottom: 1px solid #ebebeb;
    padding: 12px 16px;
    min-height: 52px;
}

#setting_row_last {
    background-color: transparent;
    border-bottom: none;
    padding: 12px 16px;
    min-height: 52px;
}

#setting_title {
    font-size: 13px;
    font-weight: 400;
    color: #1a1a1a;
}

#setting_desc {
    font-size: 12px;
    color: #6e6e6e;
}

/* ─── Buttons ──────────────────────────────── */
#btn_primary {
    padding: 7px 16px;
    background-color: #0078d4;
    color: white;
    border: 1px solid #0067b8;
    border-radius: 4px;
    font-size: 13px;
    font-weight: 600;
    min-width: 120px;
}

#btn_primary:hover {
    background-color: #0067b8;
}

#btn_primary:pressed {
    background-color: #005a9e;
}

#btn_primary:disabled {
    background-color: #b3d4ef;
    border-color: #b3d4ef;
    color: white;
}

#btn_secondary {
    padding: 7px 16px;
    background-color: #ffffff;
    color: #1a1a1a;
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    font-size: 13px;
    min-width: 90px;
}

#btn_secondary:hover {
    background-color: #f5f5f5;
}

#btn_secondary:pressed {
    background-color: #ebebeb;
}

#btn_danger {
    padding: 7px 16px;
    background-color: #ffffff;
    color: #c42b1c;
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    font-size: 13px;
    min-width: 90px;
}

#btn_danger:hover {
    background-color: #fff0ee;
    border-color: #c42b1c;
}

/* ─── Search Bar ───────────────────────────── */
#search_box {
    padding: 9px 14px;
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    background: #ffffff;
    font-size: 13px;
}

#search_box:focus {
    border: 1px solid #0078d4;
    border-bottom: 2px solid #0078d4;
}

/* ─── Table ─────────────────────────────────── */
QTableWidget {
    background-color: #ffffff;
    border: none;
    gridline-color: transparent;
    selection-background-color: #cce4f7;
    selection-color: #1a1a1a;
    alternate-background-color: #fafafa;
    outline: none;
}

QTableWidget::item {
    padding: 4px 12px;
    border-bottom: 1px solid #f0f0f0;
}

QTableWidget::item:selected {
    background-color: #cce4f7;
    color: #1a1a1a;
}

QTableWidget::item:hover {
    background-color: #f0f7ff;
}

QHeaderView::section {
    background-color: #ffffff;
    padding: 10px 12px;
    border: none;
    border-bottom: 2px solid #e5e5e5;
    font-size: 12px;
    font-weight: 600;
    color: #6e6e6e;
    letter-spacing: 0.3px;
}

QHeaderView::section:hover {
    background-color: #f5f5f5;
}

/* ─── Progress Bar ─────────────────────────── */
QProgressBar {
    border: none;
    background-color: #e5e5e5;
    border-radius: 2px;
    max-height: 3px;
    text-align: center;
}

QProgressBar::chunk {
    background-color: #0078d4;
    border-radius: 2px;
}

/* ─── Input Fields ─────────────────────────── */
QLineEdit {
    padding: 8px 12px;
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    background: #ffffff;
    font-size: 13px;
}

QLineEdit:focus {
    border-color: #0078d4;
    border-bottom: 2px solid #0078d4;
}

/* ─── List Widget ──────────────────────────── */
QListWidget {
    background-color: #fafafa;
    border: 1px solid #e5e5e5;
    border-radius: 6px;
    outline: none;
    padding: 4px;
}

QListWidget::item {
    padding: 8px 10px;
    border-radius: 4px;
    font-size: 13px;
}

QListWidget::item:selected {
    background-color: #cce4f7;
    color: #1a1a1a;
}

QListWidget::item:hover {
    background-color: #f0f0f0;
}

/* ─── ScrollBar ─────────────────────────────── */
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 14px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #c8c8c8;
    border-radius: 7px;
    min-height: 30px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background: #999999;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: transparent;
    height: 14px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #c8c8c8;
    border-radius: 7px;
    min-width: 30px;
    margin: 2px;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* ─── Tooltip ───────────────────────────────── */
QToolTip {
    background-color: #ffffff;
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    color: #1a1a1a;
    padding: 6px 10px;
    font-size: 12px;
}
"""

def apply_dark_title_bar(window, is_dark: bool):
    """
    Forces the Windows title bar to match the dark/light theme.
    """
    if window.windowHandle() is None:
        # Window not yet shown or created
        return

    import sys
    if sys.platform != "win32":
        return

    try:
        import ctypes
        from ctypes import wintypes
        
        hwnd = window.winId()
        # DWMWA_USE_IMMERSIVE_DARK_MODE: 
        #   20 for Windows 10 Build 19041+
        #   19 for older Windows 10 versions
        attribute = 20
        dark = ctypes.c_int(1 if is_dark else 0)
        
        # Try attribute 20 first
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            attribute,
            ctypes.byref(dark),
            ctypes.sizeof(dark)
        )
        if res != 0:
            # Fallback to attribute 19
            attribute = 19
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                attribute,
                ctypes.byref(dark),
                ctypes.sizeof(dark)
            )
    except Exception:
        pass
