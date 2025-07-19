from PyQt6.QtWidgets import QWidget, QLabel, QMenu, QMessageBox, QVBoxLayout
from PyQt6.QtGui import QPixmap, QMouseEvent, QDrag
from PyQt6.QtCore import Qt, QUrl, QMimeData

import platform
import os, subprocess
from datetime import datetime


def open_file_location(filepath, parent=None):
    """クロスプラットフォームでファイルのあるフォルダを開き、可能なら選択状態にする"""
    try:
        if filepath is None:
            QMessageBox.warning(parent, "エラー", f"所持していないポーションです")
            return

        abs_path = os.path.abspath(filepath)
        if not os.path.exists(abs_path):
            QMessageBox.warning(parent, "エラー", f"ファイルが見つかりません：{abs_path}")
            return

        system = platform.system()

        if system == "Windows":
            subprocess.run(['explorer', '/select,', abs_path], shell=True)

        elif system == "Darwin":  # macOS
            subprocess.run(['open', '-R', abs_path])

        elif system == "Linux":
            subprocess.run(['xdg-open', os.path.dirname(abs_path)])

        else:
            QMessageBox.warning(parent, "未対応OS", f"このOSには対応していません: {system}")

    except Exception as e:
        QMessageBox.critical(parent, "エラー", f"ファイルの場所を開く操作に失敗しました：{str(e)}")


def creation_date(path_to_file):
    """
    Try to get the date that a file was created, falling back to when it was
    last modified if that isn't possible.
    See http://stackoverflow.com/a/39501288/1709587 for explanation.
    """
    if platform.system() == 'Windows':
        return os.path.getctime(path_to_file)
    else:
        stat = os.stat(path_to_file)
        try:
            return stat.st_birthtime
        except AttributeError:
            # We're probably on Linux. No easy way to get creation dates here,
            # so we'll settle for when its content was last modified.
            return stat.st_mtime


class ClickableThumbnail(QLabel):
    def __init__(
            self, pixmap: QPixmap, fullpath: str, mtime: str, info_extracted: str,
            thumbnail_size: int, parent=None
        ):
        super().__init__(parent)

        self.selected = False
        self.clicked_callback = None
        self.thumbnail_size = thumbnail_size
        self.fullpath = fullpath
        if mtime:
            mtime = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        self.mtime = mtime
        self.info_extracted = info_extracted
        self.parent = parent
        self.original_pixmap = pixmap
        self.setPixmap(self.resize_pixmap(pixmap))
        self.setText("")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_style()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def resize_pixmap(self, pixmap):
        if self.thumbnail_size:
            pixmap = pixmap.scaled(
                self.thumbnail_size, self.thumbnail_size,
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return pixmap

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        open_folder_action = menu.addAction("ファイルの場所を開く")
        action = menu.exec(event.globalPos())
        if action == open_folder_action:
            self.open_in_explorer()

    def open_in_explorer(self):
        open_file_location(self.fullpath, parent=self)

    def leftclick(self, event):
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(self.fullpath)])
        drag.setMimeData(mime_data)
        drag.setPixmap(self.pixmap())
        drag.setHotSpot(event.position().toPoint())
        drag.exec(Qt.DropAction.CopyAction)

    def mousePressEvent(self, event: QMouseEvent):
        if self.clicked_callback:
            self.clicked_callback(self)
        self.selected = True
        self.update_style()
        if event.button() == Qt.MouseButton.LeftButton and self.fullpath:
            self.leftclick(event)
        else:
            event.accept()  # Right Click

    def update_style(self):
        if self.selected:
            self.setStyleSheet("border: 2px solid blue; border-radius: 4px;")
        else:
            self.setStyleSheet("border: 2px solid transparent; border-radius: 4px;")


class ThumbnailWidget(QWidget):
    def __init__(self, thumbnail: ClickableThumbnail, parent=None):
        super().__init__(parent)
        self.thumbnail = thumbnail
        if thumbnail.fullpath:
            self.filename = os.path.basename(thumbnail.fullpath).removesuffix(".naiv4vibe")
        else:
            self.filename = "Unknown File"

    def _base_layout(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setLayout(layout)
        return layout

    def set_clicked_callback(self, callback):
        self.thumbnail.clicked_callback = callback

    @property
    def fullpath(self):
        return self.thumbnail.fullpath

    @property
    def mtime(self):
        return self.thumbnail.mtime

    @property
    def info_extracted(self):
        return self.thumbnail.info_extracted

    def pixmap(self):
        return self.thumbnail.pixmap()

    def update_style(self):
        self.thumbnail.update_style()

    def selected(self, is_selected):
        self.thumbnail.selected = is_selected
