import platform
import os, json, subprocess
import utils
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QGridLayout, QScrollArea, QSizePolicy, QLineEdit, QPushButton, QFileDialog
)
from PyQt6.QtGui import QPixmap, QImage, QDragEnterEvent, QDropEvent, QPainter, QFont, QColor
from PyQt6.QtCore import Qt
from PIL import Image
from utils import ClickableThumbnail


def create_placeholder_pixmap(size=150) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.black)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("red"))

    font = QFont()
    font.setPointSize(int(size * 0.5))
    font.setBold(True)
    painter.setFont(font)

    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "?")
    painter.end()

    return pixmap


class ThumbnailWidget(utils.ThumbnailWidget):
    def __init__(self, thumbnail: ClickableThumbnail, strength: float, parent=None):
        super().__init__(thumbnail, parent)
        layout = self._base_layout()

        thumbnail.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        layout.addWidget(thumbnail, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Reference Strength
        label_text = f"{self.filename}\n"
        label_text += f"参照強度：{strength}"
        self.label = QLabel(label_text)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.label)

        # Text box
        self.strength_input = QLineEdit()
        self.strength_input.setPlaceholderText("参照強度を調整")
        self.strength_input.setMaximumWidth(150)
        self.strength_input.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.strength_input, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Information Extracted
        if thumbnail.info_extracted:
            info_extracted_label = QLabel(f"情報抽出度：{thumbnail.info_extracted}")
            info_extracted_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            info_extracted_label.setWordWrap(True)
            info_extracted_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            layout.addWidget(info_extracted_label)

        self.strength_input.textChanged.connect(self.update_others)
        self._strength_value = strength

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.label.setWordWrap(True)

    def update_others(self):
        try:
            base_strength = float(self.strength_input.text())
        except ValueError:
            return

        parent = self.parent()
        while parent and not hasattr(parent, 'thumbnail_widgets'):
            parent = parent.parent()
        if not parent:
            return
        parent.warning_label.setStyleSheet("color: transparent;")
        if base_strength > 1.0:
            parent.change_warning_label("large_value")

        i = parent.thumbnail_widgets.index(self)
        base = self._strength_value

        total = 0
        for j, widget in enumerate(parent.thumbnail_widgets):
            if widget is self:
                continue
            ratio = widget._strength_value / base if base != 0 else 0
            new_value = base_strength * ratio
            if abs(new_value) > 1.0:
                parent.change_warning_label("large_value")
            widget.strength_input.blockSignals(True)
            widget.strength_input.setText(f"{new_value:.8f}")
            widget.strength_input.blockSignals(False)
            total += abs(new_value)
        total += abs(float(self.strength_input.text()))

        if total < 1.0:
            parent.change_warning_label("small_total")


class PotionTabWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thumbnail_widgets = []
        self.encoding_thumbnail_map = {}  # encoding:str -> (QPixmap, info_extracted, fullpath)
        self._init_ui()

    def _init_ui(self):
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)

        self.preview_label = QLabel("画像をドロップしてください\nまたは")
        self.preview_label.setMaximumSize(300, 200)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview_label, alignment=Qt.AlignmentFlag.AlignCenter)

        button = QPushButton("画像を選択", self)
        button.setStyleSheet("font-size: 10pt;")
        button.clicked.connect(self.tmp_click)
        layout.addWidget(button)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.thumb_widget = QWidget()
        self.thumb_layout = QGridLayout(self.thumb_widget)
        self.thumb_layout.setContentsMargins(10, 10, 10, 10)
        self.thumb_layout.setSpacing(15)

        self.scroll_area.setWidget(self.thumb_widget)
        layout.addWidget(self.scroll_area)

        self.warnings = {
            "small_total": "警告：参照強度の合計が1.0未満です",
            "large_value": "警告：1.0を超える参照強度があります",
        }
        self.warning_label = QLabel(self.warnings["small_total"])
        self.warning_label.setStyleSheet("color: transparent;")
        layout.addWidget(self.warning_label, alignment=Qt.AlignmentFlag.AlignHCenter)

    def tmp_click(self):
        filepath, _ = QFileDialog.getOpenFileName(
            parent=self,
            caption="ファイルを選択",
            directory="",
            filter="画像ファイル (*.png *.webp)")
        self.handle_dropped_image(filepath)

    def change_warning_label(self, mode):
        if mode not in self.warnings:
            return
        text = self.warnings[mode]
        self.warning_label.setText(text)
        self.warning_label.setStyleSheet("color: red;")

    def set_encoding_thumbnail_map(self, mapping):
        self.encoding_thumbnail_map = mapping

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".png"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath.lower().endswith(".png"):
                self.handle_dropped_image(filepath)

    def handle_dropped_image(self, filepath):
        self.clear_thumbnails()

        # プレビュー表示
        image = QImage(filepath)
        pixmap = QPixmap.fromImage(image)
        pixmap = pixmap.scaled(
            self.preview_label.maximumSize(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.preview_label.setPixmap(pixmap)

        try:
            img = Image.open(filepath)
            comment = img.info.get("Comment")
            if not comment:
                raise ValueError("no comment")
            info = json.loads(comment)

            keys = info.get("reference_image_multiple", None)
            if not keys:
                self.preview_label.setText("ポーションなし")
                return
            else:
                strengths = info["reference_strength_multiple"]
        except Exception:
            self.preview_label.setText("メタデータ無し")
            return

        for idx, key in enumerate(keys):
            pixmap, info_extracted, fullpath = self.encoding_thumbnail_map.get(key, (None, None, None))

            if not pixmap:
                pixmap = create_placeholder_pixmap(150)

            label_widget = ThumbnailWidget(
                ClickableThumbnail(pixmap, fullpath, None, info_extracted, thumbnail_size=128, parent=self),
                strengths[idx])
            label_widget.set_clicked_callback(self.clear_selection_except)
            self.thumbnail_widgets.append(label_widget)

            row = idx // 4
            col = idx % 4
            self.thumb_layout.addWidget(label_widget, row, col)

    def clear_thumbnails(self):
        self.thumbnail_widgets.clear()
        while self.thumb_layout.count():
            item = self.thumb_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def clear_selection_except(self, selected_widget):
        for widget in self.thumbnail_widgets:
            if widget is not selected_widget:
                widget.selected(False)
                widget.update_style()
