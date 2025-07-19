import sys
import os
import json
import re
import base64
import utils
from pathlib import Path
from math import cos, sin, pi
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QMenuBar, QMenu, QLabel, QFileDialog,
    QMessageBox, QDialog, QListWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLineEdit
)
from PyQt6.QtGui import QAction, QPixmap, QImage, QActionGroup, QColor, QPainter, QFont
from PyQt6.QtCore import Qt, QTimer
from browse_tab_widget import BrowseTabWidget
from potion_tab_widget import PotionTabWidget

CONFIG_FILE = "config.json"
default_config = {
    "version": "v4.5",
    "thumbnail_size": 128,
    "directories": [],
    "sort_order": "name_asc",
    "window_width": 800,
    "window_height": 600,
    "show_images_without_thumbnails": False}


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default_config


def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"設定ファイルの保存に失敗しました: {e}")


def create_placeholder_image(size=128) -> QImage:
    """サムネイルが無い場合の代替画像を描画（ドットが円状に並んだ画像）"""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(15, 15, 40))  # 背景色

    painter = QPainter()
    try:
        if not painter.begin(image):
            raise RuntimeError("QPainter の初期化に失敗しました。")

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = size / 2
        radius = size * 0.35
        dot_radius = size * 0.04
        num_dots = 12

        for i in range(num_dots):
            angle = 2 * pi * i / num_dots
            x = center + radius * cos(angle)
            y = center + radius * sin(angle)

            color = QColor("#0000aa") if i % 2 == 0 else QColor("#8b5e3c")
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                int(x - dot_radius),
                int(y - dot_radius),
                int(dot_radius * 2),
                int(dot_radius * 2)
            )
        painter.setPen(QColor("red"))
        font = QFont()
        font.setPointSize(int(size * 0.12))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, "No Image")
    finally:
        painter.end()

    return image


def get_b64thumbnail(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    b64_thumb = data.get("thumbnail")
    if not b64_thumb:
        no_thumb = True
        image = create_placeholder_image()
    else:
        no_thumb = False
        b64_thumb = re.sub('^data:image/.+;base64,', '', b64_thumb).encode('utf-8')
        image_data = base64.b64decode(b64_thumb)
        image = QImage.fromData(image_data)
    return data, image, no_thumb


class DirectorySettingsDialog(QDialog):
    def __init__(self, directories, parent=None):
        super().__init__(parent)
        self.setWindowTitle("検索対象ディレクトリの設定")
        self.resize(600, 400)

        self.directories = directories.copy()

        self.list_widget = QListWidget()
        self.list_widget.addItems(self.directories)

        add_button = QPushButton("追加")
        remove_button = QPushButton("削除")
        close_button = QPushButton("閉じる")

        add_button.clicked.connect(self.add_directory)
        remove_button.clicked.connect(self.remove_selected)
        close_button.clicked.connect(self.accept)

        button_layout = QVBoxLayout()
        button_layout.addWidget(add_button)
        button_layout.addWidget(remove_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)

        main_layout = QHBoxLayout(self)
        main_layout.addWidget(self.list_widget)
        main_layout.addLayout(button_layout)

    def add_directory(self):
        folder = QFileDialog.getExistingDirectory(self, "フォルダを追加")
        if folder and folder not in self.directories:
            self.directories.append(folder)
            self.list_widget.addItem(folder)

    def remove_selected(self):
        selected_items = self.list_widget.selectedItems()
        for item in selected_items:
            path = item.text()
            self.directories.remove(path)
            self.list_widget.takeItem(self.list_widget.row(item))

    def get_directories(self):
        return self.directories


class Naiv4VibeViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("naiv4vibe Viewer - PyQt6")
        self.config = load_config()
        width = self.config["window_width"]
        height = self.config["window_height"]
        self.resize(width, height)
        self.thumbnail_size = self.config["thumbnail_size"]
        self.show_images_without_thumbnails = self.config["show_images_without_thumbnails"]

        self.directories = self.config["directories"]
        for i, d in enumerate(self.directories):
            if not os.path.exists(d):
                del self.directories[i]
        self.sort_order = self.config["sort_order"]
        self.version = self.config["version"]

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.browse_tab = BrowseTabWidget(self)
        self.tabs.addTab(self.browse_tab, "ブラウズ")

        self.encoding_thumbnail_map = {}
        self.potion_tab = PotionTabWidget(self)
        self.potion_tab.set_encoding_thumbnail_map(self.encoding_thumbnail_map)
        self.tabs.addTab(self.potion_tab, "ポーション確認")

        self.setup_menu()

        if self.directories:
            QTimer.singleShot(0, self.load_files)

    def setup_menu(self):
        menu_bar = QMenuBar(self)

        folder_action = QAction("フォルダ設定", self)
        folder_action.triggered.connect(self.select_folders)

        reload_action = QAction("更新", self)
        reload_action.triggered.connect(self.load_files)

        config_menu = QMenu("設定", self)

        size_action = QAction("表示サイズ変更", self)
        size_action.triggered.connect(self.change_thumbnail_size)
        config_menu.addAction(size_action)

        sort_menu = QMenu("並び替え", self)
        sort_actions = {
            "name_asc":  QAction("ファイル名 昇順", self),
            "name_desc": QAction("ファイル名 降順", self),
            "time_desc": QAction("新しい順", self),
            "time_asc":  QAction("古い順", self),
        }
        sort_actions[self.sort_order].setChecked(True)
        sort_group = QActionGroup(self)
        sort_group.setExclusive(True)

        for key, action in sort_actions.items():
            action.setCheckable(True)
            sort_group.addAction(action)
            action.triggered.connect(lambda checked, o=key: self.set_sort_order(o))
            sort_menu.addAction(action)
        config_menu.addMenu(sort_menu)

        self.toggle_no_thumbnail_action = QAction("サムネイルの無いポーションも表示する", self, checkable=True)
        self.toggle_no_thumbnail_action.setChecked(self.show_images_without_thumbnails)
        self.toggle_no_thumbnail_action.triggered.connect(self.toggle_no_thumbnail_display)
        config_menu.addAction(self.toggle_no_thumbnail_action)

        version_menu = QMenu("version切り替え", self)
        version_actions = {
            "v4.5": QAction("V4.5", self),
            "v4.5c": QAction("V4.5 Curated", self),
            "v4": QAction("V4", self),
            "v4c": QAction("V4 Curated", self),
        }
        version_actions[self.version].setChecked(True)
        version_group = QActionGroup(self)
        version_group.setExclusive(True)

        for key, action in version_actions.items():
            action.setCheckable(True)
            version_group.addAction(action)
            action.triggered.connect(lambda checked, o=key: self.set_version(o))
            version_menu.addAction(action)
        config_menu.addMenu(version_menu)

        menu_bar.addAction(folder_action)
        menu_bar.addAction(reload_action)
        menu_bar.addMenu(config_menu)
        self.setMenuBar(menu_bar)

    def set_version(self, version):
        self.version = version
        self.config["version"] = version
        save_config(self.config)
        self.load_files()

    def set_sort_order(self, order):
        self.sort_order = order
        self.config["sort_order"] = order
        save_config(self.config)
        self.browse_tab.sort_thumbnails(order)
        self.reload_files()

    def select_folders(self):
        dialog = DirectorySettingsDialog(self.directories, self)
        if dialog.exec():
            self.directories = dialog.get_directories()
            self.config["directories"] = self.directories
            save_config(self.config)
            self.load_files()

    def toggle_no_thumbnail_display(self):
        self.show_images_without_thumbnails = self.toggle_no_thumbnail_action.isChecked()
        self.config['show_images_without_thumbnails'] = self.show_images_without_thumbnails
        save_config(self.config)
        self.reload_files()

    def reload_files(self):
        self.browse_tab.set_view()

    def change_thumbnail_size(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("表示サイズの変更")

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("画像の表示サイズ（ピクセル、50～500）："))

        input_box = QLineEdit()
        input_box.setText(str(self.thumbnail_size))
        layout.addWidget(input_box)

        apply_button = QPushButton("適用")
        layout.addWidget(apply_button)

        def apply_size():
            text = input_box.text()
            if text.isdigit():
                new_size = int(text)
                if 50 <= new_size <= 500:
                    self.thumbnail_size = new_size
                    self.config["thumbnail_size"] = new_size
                    save_config(self.config)
                    self.reload_files()
                    dialog.accept()
                else:
                    QMessageBox.warning(dialog, "無効な値", "50～500の範囲内で指定してください。")
            else:
                QMessageBox.warning(dialog, "無効な入力", "数値を入力してください。")

        apply_button.clicked.connect(apply_size)
        dialog.exec()

    def load_files(self):
        items = []
        error_messages = []

        self.browse_tab.reset_registrated_thumbnails()
        for directory in self.directories:
            files = [f for f in os.listdir(directory) if f.endswith(".naiv4vibe")]

            for filename in files:
                filepath = os.path.join(directory, filename)
                try:
                    data, image, no_thumb = get_b64thumbnail(filepath)
                    if image is None or image.isNull():
                        continue

                    if self.version == "v4":
                        version_key = "v4full"
                    elif self.version == "v4.5":
                        version_key = "v4-5full"
                    elif self.version == "v4.5c":
                        version_key = "v4-5curated"
                    elif self.version == "v4c":
                        version_key = "v4curated"
                    else:
                        continue

                    encodings = data.get("encodings", {}).get(version_key, {})
                    if not len(encodings):
                        continue

                    pixmap = QPixmap.fromImage(image)
                    # mtime = os.path.getmtime(filepath)
                    mtime = utils.creation_date(filepath)
                    info = []
                    for item in encodings.values():
                        enc = item.get("encoding", {})
                        if not enc:
                            continue

                        params = item.get("params", {})
                        info_extracted = params.get("information_extracted")

                        if isinstance(info_extracted, (float, int)):
                            info.append(f"{info_extracted}")

                        current = self.encoding_thumbnail_map.get(enc)
                        to_be_update = not current or (not current[1] and info_extracted)
                        self.encoding_thumbnail_map[enc] = (pixmap, info_extracted, filepath) if to_be_update else current

                    importinfo = data.get("importInfo", {})
                    self.browse_tab.register_thumbnail(
                        pixmap, filepath, mtime, ", ".join(sorted(info)), importinfo, no_thumb
                    )

                except Exception as e:
                    error_messages.append(f"[エラー] {filename}: {str(e)}")

        self.set_sort_order(self.sort_order)
        if error_messages:
            QMessageBox.warning(self, "読み込みエラー", "\n".join(error_messages))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.browse_tab.set_view()

    def closeEvent(self, event):
        size = self.size()
        self.config["window_width"] = size.width()
        self.config["window_height"] = size.height()
        save_config(self.config)
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = Naiv4VibeViewer()
    viewer.show()
    sys.exit(app.exec())
