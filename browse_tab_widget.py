import os
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QLineEdit, QSizePolicy, QGridLayout, QMessageBox,
    QInputDialog, QComboBox, QMenu, QFrame, QPushButton
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QMouseEvent, QShortcut, QKeySequence, QDoubleValidator
from datetime import datetime
import utils
from send2trash import send2trash
from collections import OrderedDict


def insert_linebreaks(text: str, max_chars_per_line: int = 10) -> str:
    """指定文字数ごとに改行を挿入する"""
    return '\n'.join(text[i:i+max_chars_per_line] for i in range(0, len(text), max_chars_per_line))


class ClickableThumbnail(utils.ClickableThumbnail):
    def __init__(
            self, pixmap: QPixmap, fullpath: str, mtime: str, info_extracted: str,
            importinfo: dict, thumbnail_size: int, parent=None
        ):
        super().__init__(pixmap, fullpath, mtime, info_extracted, thumbnail_size, parent=parent)
        self.filename = os.path.basename(self.fullpath)
        self.importinfo = importinfo

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        rename_action = menu.addAction("名前の変更")
        delete_action = menu.addAction("削除")
        open_folder_action = menu.addAction("ファイルの場所を開く")

        action = menu.exec(event.globalPos())

        if action == rename_action:
            self.rename_file()
        elif action == delete_action:
            self.delete_file()
        elif action == open_folder_action:
            self.open_in_explorer()

    def rename_file(self):
        base_name = os.path.splitext(self.filename)[0]
        new_name, ok = QInputDialog.getText(self, "名前の変更", "新しい名前を入力してください：", text=base_name)
        if ok and new_name:
            new_filename = new_name + ".naiv4vibe"
            new_path = os.path.join(os.path.dirname(self.fullpath), new_filename)

            if os.path.exists(new_path):
                QMessageBox.critical(self, "エラー", "同名のファイルが既に存在します。")
                return

            try:
                os.rename(self.fullpath, new_path)
                self.fullpath = new_path
                self.filename = new_filename
                self.parent.main_window.load_files()

            except Exception as e:
                QMessageBox.critical(self, "エラー", f"名前の変更に失敗しました：{str(e)}")

    def delete_file(self):
        reply = QMessageBox.question(
            self, "確認", f"{self.filename} をゴミ箱に移動しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                abs_path = os.path.abspath(self.fullpath)
                if not os.path.exists(abs_path):
                    raise FileNotFoundError(f"ファイルが存在しません: {abs_path}")
                send2trash(abs_path)

                self.parent.main_window.load_files()
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"削除に失敗しました：{str(e)}")

    def mousePressEvent(self, event: QMouseEvent):
        if self.clicked_callback:
            self.clicked_callback(self)
        self.selected = True
        self.update_style()
        if event.button() == Qt.MouseButton.LeftButton and self.fullpath:
            self.leftclick(event)
        else:
            event.accept()  # Right Click
        self.parent.update_detail_from_thumbnail(self)

    def set_importinfo(self, importinfo):
        with open(self.fullpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data["importInfo"] = importinfo
        with open(self.fullpath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)


class ThumbnailWidget(utils.ThumbnailWidget):
    def __init__(self, thumbnail: ClickableThumbnail, parent=None):
        super().__init__(thumbnail, parent)
        layout = self._base_layout()

        thumbnail.setFixedSize(thumbnail.thumbnail_size, thumbnail.thumbnail_size)
        thumbnail.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(thumbnail, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.label = QLabel(insert_linebreaks(self.filename, max_chars_per_line=16))
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(self.label)


class BrowseTabWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.items = []
        self.thumbnails = []
        self.current_selection = None
        self.outer_layout = QVBoxLayout(self)

        self.search_query = ""
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("ファイル名で検索...")
        self.search_box.returnPressed.connect(self.apply_search_filter_from_textbox)
        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(self.focus_search_box)
        self.outer_layout.addWidget(self.search_box)

        self.main_layout = QHBoxLayout()
        self.outer_layout.addLayout(self.main_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(4)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)

        self.grid_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scroll_area.setWidget(self.grid_widget)
        self.main_layout.addWidget(self.scroll_area, stretch=1)

        self.detail_panel = QWidget()
        self.detail_panel.setFixedWidth(256)
        self.main_layout.addWidget(self.detail_panel)

        self.init_detail_panel()

        self.reset_registrated_thumbnails()

    def init_detail_panel(self):
        layout = QVBoxLayout(self.detail_panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.detail_image = QLabel()
        self.detail_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.detail_image)

        self.detail_filename = QLabel("ファイル名：")
        self.detail_filename.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.detail_filename.setStyleSheet("font-size: 12pt;")
        self.detail_filename.setWordWrap(True)
        self.detail_filename.setMaximumWidth(230)
        layout.addWidget(self.detail_filename)

        self.detail_mtime = QLabel("作成日時：")
        self.detail_mtime.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.detail_mtime.setStyleSheet("font-size: 12pt;")
        layout.addWidget(self.detail_mtime)

        self.detail_info_extracted = QLabel("情報抽出度：")
        self.detail_info_extracted.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.detail_info_extracted.setStyleSheet("font-size: 12pt;")
        self.detail_info_extracted.setWordWrap(True)
        self.detail_info_extracted.setMaximumWidth(230)
        layout.addWidget(self.detail_info_extracted)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        layout.insertWidget(-1, line)

        detail_importinfo = QLabel("読み込み設定：")
        detail_importinfo.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        detail_importinfo.setStyleSheet("font-size: 12pt;")
        detail_importinfo.setWordWrap(True)
        detail_importinfo.setMaximumWidth(230)
        layout.addWidget(detail_importinfo)

        self.version_choices = [
            "nai-diffusion-4-full", "nai-diffusion-4-5-full", "nai-diffusion-4-5-curated", "nai-diffusion-4-curated-preview"
        ]
        self.import_version_select = QComboBox()
        self.import_version_select.setStyleSheet("font-size: 10pt;")
        for v in self.version_choices:
            self.import_version_select.addItem(v)
        layout.addWidget(self.import_version_select)

        import_strength_layout = QHBoxLayout()
        text = QLabel("参照強度：")
        text.setStyleSheet("font-size: 10pt;")
        validator = QDoubleValidator()
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.import_strength = QLineEdit()
        self.import_strength.setMaximumWidth(100)
        self.import_strength.setValidator(validator)
        import_strength_layout.addWidget(text)
        import_strength_layout.addWidget(self.import_strength)
        import_strength_layout.addStretch()
        layout.addLayout(import_strength_layout)

        import_info_extracted_layout = QHBoxLayout()
        text = QLabel("情報抽出度：")
        text.setStyleSheet("font-size: 10pt;")
        validator = QDoubleValidator(0.0, 1.0, 12)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.import_info_extracted = QLineEdit()
        self.import_info_extracted.setMaximumWidth(100)
        self.import_info_extracted.setValidator(validator)
        import_info_extracted_layout.addWidget(text)
        import_info_extracted_layout.addWidget(self.import_info_extracted)
        import_info_extracted_layout.addStretch()
        layout.addLayout(import_info_extracted_layout)

        button = QPushButton("設定保存", self)
        button.setStyleSheet("font-size: 10pt;")
        button.clicked.connect(self.save_importinfo)
        button.setDefault(True)
        layout.addWidget(button)

        layout.addStretch()

    def clear_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                self.grid_layout.removeWidget(widget)
        self.thumbnails = []

    def reset_registrated_thumbnails(self):
        self.clear_grid()
        self.items = []

    @property
    def has_thumbnails(self):
        if self.items:
            return True
        return False

    def focus_search_box(self):
        self.search_box.setFocus()
        self.search_box.selectAll()

    def apply_search_filter_from_textbox(self):
        self.search_query = self.search_box.text().strip()
        self.set_view()

    def sort_thumbnails(self, sort_order):
        if sort_order == "name_asc":
            self.items.sort(key=lambda x: os.path.basename(x[1]).removesuffix(".naiv4vibe"))
        elif sort_order == "name_desc":
            self.items.sort(key=lambda x: os.path.basename(x[1]).removesuffix(".naiv4vibe"), reverse=True)
        elif sort_order == "time_asc":
            self.items.sort(key=lambda x: datetime.fromtimestamp(x[2]).strftime("%Y-%m-%d %H:%M:%S"))
        elif sort_order == "time_desc":
            self.items.sort(key=lambda x: datetime.fromtimestamp(x[2]).strftime("%Y-%m-%d %H:%M:%S"), reverse=True)
        else:
            raise NotImplementedError("The sort order is not implemented.")

    def register_thumbnail(self, pixmap, filepath, mtime, info, importinfo, no_thumb):
        thumb_info = (pixmap, filepath, mtime, info, importinfo, no_thumb)
        self.items.append(thumb_info)

    def set_view(self):
        self.clear_grid()
        thumbs = self.items
        if self.search_query:
            query_lower = self.search_query.lower()
            thumbs = [
                t for t in thumbs
                if query_lower in os.path.basename(t[1]).removesuffix(".naiv4vibe").lower()
            ]

        # グリッド幅に応じた列数を計算
        available_width = self.scroll_area.viewport().width()
        if thumbs:
            widget_width = self.main_window.thumbnail_size + 30  # サムネイルとマージン、ラベル含む想定値
            columns = max(1, available_width // widget_width)
        else:
            columns = 1

        idx = 0
        for thumb_info in thumbs:
            row = idx // columns
            col = idx % columns
            pixmap, filepath, mtime, info, importinfo, no_thumb = thumb_info
            if no_thumb and not self.main_window.show_images_without_thumbnails:
                continue
            widget = ThumbnailWidget(
                ClickableThumbnail(pixmap, filepath, mtime, info, importinfo, self.main_window.thumbnail_size, parent=self),
                parent=self
            )
            widget.set_clicked_callback(self.clear_selection_except)
            self.thumbnails.append(widget)
            self.grid_layout.addWidget(widget, row, col)
            idx += 1

    def update_detail_from_thumbnail(self, thumb: ClickableThumbnail):
        self.current_selection = thumb
        pixmap = thumb.original_pixmap
        importinfo = thumb.importinfo
        self.detail_image.setPixmap(
            pixmap.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.detail_filename.setText(f"ファイル名：{os.path.basename(thumb.fullpath).removesuffix('.naiv4vibe')}")
        self.detail_mtime.setText(f"作成日時：{thumb.mtime}")
        self.detail_info_extracted.setText(f"情報抽出度：{thumb.info_extracted}")
        self.import_strength.setText(str(importinfo["strength"]))
        self.import_info_extracted.setText(str(importinfo["information_extracted"]))
        self.import_version_select.setCurrentIndex(self.version_choices.index(importinfo["model"]))

    def save_importinfo(self):
        if self.current_selection:
            information_extracted = float(self.import_info_extracted.text())
            if not (0.01 <= information_extracted <= 1):
                QMessageBox.critical(self, "エラー", "情報抽出度は0.01～1.0の範囲で入力してください。")
            else:
                importinfo = {
                    "model": self.import_version_select.currentText(),
                    "information_extracted": information_extracted,
                    "strength": float(self.import_strength.text()),
                }
                self.current_selection.set_importinfo(importinfo)
                QMessageBox.information(self, "保存完了", "読み込み設定が保存されました。")

    def clear_selection_except(self, selected_widget: ClickableThumbnail):
        for widget in self.thumbnails:
            if widget is not selected_widget:
                widget.selected(False)
                widget.update_style()