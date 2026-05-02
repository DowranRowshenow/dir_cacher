import os
import sqlite3
import base64
from PySide6.QtWidgets import QFileIconProvider
from PySide6.QtCore import QFileInfo, QSize, QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QIcon, QPixmap

class IconProvider:
    def __init__(self, db_path="icons.db"):
        self.db_path = db_path
        self._provider = QFileIconProvider()
        self._memory_cache = {}
        self._init_db()

    def _init_db(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS icon_cache (ext TEXT PRIMARY KEY, data TEXT)")

    def get_icon(self, path, is_dir=False):
        ext = "folder" if is_dir else os.path.splitext(path)[1].lower()
        if not ext: ext = "file"
        
        if ext in self._memory_cache:
            return self._memory_cache[ext]
        
        # Check DB
        cursor = self.conn.execute("SELECT data FROM icon_cache WHERE ext = ?", (ext,))
        row = cursor.fetchone()
        if row:
            pixmap = self._base64_to_pixmap(row[0])
            icon = QIcon(pixmap)
            self._memory_cache[ext] = icon
            return icon
        
        # Fetch from system
        icon = self._fetch_system_icon(path, is_dir)
        if icon:
            pixmap = icon.pixmap(QSize(32, 32))
            b64 = self._pixmap_to_base64(pixmap)
            try:
                with self.conn:
                    self.conn.execute("INSERT OR REPLACE INTO icon_cache (ext, data) VALUES (?, ?)", (ext, b64))
            except: pass
            self._memory_cache[ext] = icon
            return icon
        
        return QIcon()

    def _fetch_system_icon(self, path, is_dir):
        # We try to use QFileIconProvider.
        # For extensions, we might need a dummy file if the path doesn't exist.
        if is_dir:
            return self._provider.icon(QFileIconProvider.Folder)
        
        if os.path.exists(path):
            return self._provider.icon(QFileInfo(path))
        else:
            # Standard file icon or try to get by extension
            return self._provider.icon(QFileIconProvider.File)

    def _pixmap_to_base64(self, pixmap):
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.WriteOnly)
        pixmap.save(buffer, "PNG")
        return base64.b64encode(byte_array.data()).decode()

    def _base64_to_pixmap(self, b64):
        data = base64.b64decode(b64)
        pixmap = QPixmap()
        pixmap.loadFromData(data, "PNG")
        return pixmap
