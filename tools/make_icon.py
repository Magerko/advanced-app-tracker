"""Regenerate app_tracker/resources/app_icon.png. Run: python tools/make_icon.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QApplication

from app_tracker.resources import APP_ICON_PATH

SIZE = 256


def render() -> QImage:
    image = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Rounded background with a blue gradient.
    gradient = QLinearGradient(0, 0, SIZE, SIZE)
    gradient.setColorAt(0.0, QColor(42, 130, 218))
    gradient.setColorAt(1.0, QColor(25, 70, 130))
    painter.setBrush(QBrush(gradient))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(8, 8, SIZE - 16, SIZE - 16), 48, 48)

    # Clock face.
    center = QPointF(SIZE / 2, SIZE / 2)
    radius = SIZE * 0.30
    painter.setBrush(QBrush(QColor(245, 245, 245)))
    painter.drawEllipse(center, radius, radius)

    # Clock hands.
    painter.setPen(QPen(QColor(40, 40, 40), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(center, QPointF(center.x(), center.y() - radius * 0.6))
    painter.drawLine(center, QPointF(center.x() + radius * 0.45, center.y()))
    painter.setBrush(QBrush(QColor(40, 40, 40)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(center, 9, 9)

    painter.end()
    return image


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841 (QPainter needs a QApplication)
    image = render()
    APP_ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
    if image.save(str(APP_ICON_PATH), "PNG"):
        print(f"Wrote {APP_ICON_PATH}")
    else:
        print("Failed to write icon", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
