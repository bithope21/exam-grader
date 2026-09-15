"""Small, keyboard-operable four-corner editor for low-confidence page crops."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from exam_grader.document_normalization import validate_manual_corners

CORNER_LABELS = ("ซ้ายบน", "ขวาบน", "ขวาล่าง", "ซ้ายล่าง")


class _CornerHandle(QGraphicsEllipseItem):
    def __init__(self, number: int, point: QPointF, bounds: QRectF, changed) -> None:
        super().__init__(-14.0, -14.0, 28.0, 28.0)
        self.number = number
        self.bounds = bounds
        self.changed = changed
        self.setPos(point)
        self.setBrush(QBrush(QColor("#047857")))
        self.setPen(QPen(QColor("#ffffff"), 2.0))
        self.setZValue(3.0)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(
            f"มุม {number}: {CORNER_LABELS[number - 1]} · ลากเพื่อปรับ หรือใช้ปุ่มลูกศร"
        )

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            x = min(max(float(value.x()), self.bounds.left()), self.bounds.right())
            y = min(max(float(value.y()), self.bounds.top()), self.bounds.bottom())
            return QPointF(x, y)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.changed()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        painter.drawEllipse(QRectF(-14.0, -14.0, 28.0, 28.0))
        painter.setPen(QPen(QColor("#ffffff")))
        font = QFont()
        font.setPointSize(11)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(QRectF(-10.0, -10.0, 20.0, 20.0), Qt.AlignmentFlag.AlignCenter, str(self.number))

    def keyPressEvent(self, event) -> None:
        directions = {
            Qt.Key.Key_Left: (-1.0, 0.0),
            Qt.Key.Key_Right: (1.0, 0.0),
            Qt.Key.Key_Up: (0.0, -1.0),
            Qt.Key.Key_Down: (0.0, 1.0),
        }
        direction = directions.get(event.key())
        if direction is None:
            super().keyPressEvent(event)
            return
        step = 10.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
        self.setPos(self.pos() + QPointF(direction[0] * step, direction[1] * step))
        event.accept()

    def mousePressEvent(self, event) -> None:
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.CursorShape.OpenHandCursor)


class ManualCropDialog(QDialog):
    """Let a teacher correct a detected page quad before OMR is rerun."""

    def __init__(
        self,
        image: np.ndarray,
        corners: np.ndarray | list[list[float]],
        *,
        target_size: tuple[int, int],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("ปรับกรอบกระดาษ 4 มุม")
        self.resize(960, 760)
        self.setMinimumSize(720, 560)
        self.image = image
        self.target_size = target_size
        self._accepted_corners: np.ndarray | None = None
        self._initial_corners = np.asarray(corners, dtype=np.float32).reshape(4, 2).copy()

        layout = QVBoxLayout(self)
        self.hint = QLabel(
            "ลากจุด 1–4 ให้ตรงกับมุมกระดาษ แล้วกด “จัดแนวและตรวจใหม่”\n"
            "ถ้าขอบถูกบังหรือหาไม่ครบ อย่าฝืนเลือกกรอบ ให้ยกเลิกแล้วถ่ายใหม่"
        )
        self.hint.setWordWrap(True)
        self.hint.setAccessibleName("คำแนะนำการปรับกรอบกระดาษ")
        layout.addWidget(self.hint)

        height, width = image.shape[:2]
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(QRectF(0.0, 0.0, float(width - 1), float(height - 1)))
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        qimage = QImage(
            rgb.data,
            rgb.shape[1],
            rgb.shape[0],
            rgb.strides[0],
            QImage.Format.Format_RGB888,
        ).copy()
        self.scene.addItem(QGraphicsPixmapItem(QPixmap.fromImage(qimage)))

        self.polygon = QGraphicsPolygonItem()
        polygon_pen = QPen(QColor("#00a889"), 3.0, Qt.PenStyle.SolidLine)
        polygon_pen.setCosmetic(True)
        self.polygon.setPen(polygon_pen)
        self.polygon.setBrush(QBrush(QColor(0, 168, 137, 38)))
        self.polygon.setZValue(2.0)
        self.scene.addItem(self.polygon)
        bounds = self.scene.sceneRect()
        self.handles = [
            _CornerHandle(index + 1, QPointF(float(point[0]), float(point[1])), bounds, self._refresh_polygon)
            for index, point in enumerate(self._initial_corners)
        ]
        for handle in self.handles:
            self.scene.addItem(handle)

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.view.setBackgroundBrush(QBrush(QColor("#20252b")))
        self.view.setAccessibleName("ภาพต้นฉบับพร้อมจุดปรับมุมกระดาษ")
        layout.addWidget(self.view, stretch=1)

        actions = QHBoxLayout()
        self.reset_button = QPushButton("คืนมุมที่ตรวจพบ")
        self.reset_button.clicked.connect(self.reset_corners)
        actions.addWidget(self.reset_button)
        actions.addStretch(1)
        self.cancel_button = QPushButton("ยกเลิก")
        self.cancel_button.clicked.connect(self.reject)
        actions.addWidget(self.cancel_button)
        self.apply_button = QPushButton("จัดแนวและตรวจใหม่")
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self._accept_corners)
        actions.addWidget(self.apply_button)
        layout.addLayout(actions)

        self._refresh_polygon()
        QTimer.singleShot(0, self._fit_image)

    def _fit_image(self) -> None:
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_image()

    def _refresh_polygon(self) -> None:
        points = [handle.pos() for handle in getattr(self, "handles", [])]
        if len(points) == 4:
            self.polygon.setPolygon(QPolygonF(points))

    def reset_corners(self) -> None:
        for handle, point in zip(self.handles, self._initial_corners):
            handle.setPos(QPointF(float(point[0]), float(point[1])))
        self._refresh_polygon()

    def current_corners(self) -> np.ndarray:
        return np.asarray([[handle.pos().x(), handle.pos().y()] for handle in self.handles], dtype=np.float32)

    def _accept_corners(self) -> None:
        try:
            self._accepted_corners = validate_manual_corners(
                self.current_corners(), self.image.shape, target_size=self.target_size
            )
        except ValueError as error:
            self.hint.setText(f"{error}\nปรับมุมให้เป็นกรอบกระดาษครบทั้ง 4 ด้าน หรือยกเลิกเพื่อถ่ายใหม่")
            self.hint.setProperty("role", "warning")
            self.hint.style().unpolish(self.hint)
            self.hint.style().polish(self.hint)
            return
        super().accept()

    def accepted_corners(self) -> np.ndarray | None:
        return None if self._accepted_corners is None else self._accepted_corners.copy()
