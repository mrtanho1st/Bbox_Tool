"""Scene coordinates equal image pixels; zoom only affects the view transform."""

from copy import deepcopy
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPen, QColor, QPainter, QImage
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PIL import Image
from app.core.model import Box


class Canvas(QGraphicsView):
    edited = Signal(object)
    selected = Signal(int)
    zoomed = Signal(float)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#111720"))
        self.mode = "Draw"
        self.boxes = []
        self.names = []
        self.colors = []
        self.active_class = None
        self.selection = -1
        self.w = 0
        self.h = 0
        self.start = None
        self.original = None
        self.preview = None
        self.draft_points = []
        self.items_drawn = []
        self.show_boxes = True
        self.show_labels = True
        self.grid = False
        self.setMouseTracking(True)

    def load(self, path):
        with Image.open(path) as im:
            rgb = im.convert("RGB")
            self.w, self.h = rgb.size
            raw = rgb.tobytes()
            q = QImage(
                raw, self.w, self.h, self.w * 3, QImage.Format.Format_RGB888
            ).copy()
        self.scene().clear()
        self.items_drawn = []
        self.scene().addPixmap(QPixmap.fromImage(q))
        self.setSceneRect(0, 0, self.w, self.h)
        self.boxes = []
        self.selection = -1
        self.start = None
        self.original = None
        self.preview = None
        self.draft_points = []
        self.fit()

    def fit(self):
        if self.w:
            self.fitInView(
                QRectF(0, 0, self.w, self.h), Qt.AspectRatioMode.KeepAspectRatio
            )
            self.zoomed.emit(self.transform().m11())

    def zoom(self, factor):
        value = self.transform().m11() * factor
        if 0.005 < value < 50:
            self.scale(factor, factor)
            self.zoomed.emit(self.transform().m11())
            self.render_boxes()

    def wheelEvent(self, event):
        pos = event.position().toPoint()
        anchor = self.mapToScene(pos)
        self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
        shifted = self.mapToScene(pos) - anchor
        self.translate(shifted.x(), shifted.y())
        event.accept()

    def set_mode(self, mode):
        self.mode = mode
        self.start = None
        self.preview = None
        self.draft_points = []
        self.setDragMode(
            QGraphicsView.DragMode.ScrollHandDrag
            if mode == "Pan"
            else QGraphicsView.DragMode.NoDrag
        )
        self.setCursor(
            Qt.CursorShape.CrossCursor if mode == "Draw" else Qt.CursorShape.ArrowCursor
        )
        self.render_boxes()

    def point(self, pos):
        p = self.mapToScene(pos)
        return QPointF(max(0, min(self.w, p.x())), max(0, min(self.h, p.y())))

    def render_boxes(self):
        for item in self.items_drawn:
            self.scene().removeItem(item)
        self.items_drawn = []
        scale = max(0.001, self.transform().m11())
        point_pen = QPen(QColor("#62e8c2"), 2)
        point_pen.setCosmetic(True)
        for index, point in enumerate(self.draft_points):
            if index:
                self.items_drawn.append(
                    self.scene().addLine(
                        self.draft_points[index - 1].x(),
                        self.draft_points[index - 1].y(),
                        point.x(),
                        point.y(),
                        point_pen,
                    )
                )
            size = 8 / scale
            marker = self.scene().addEllipse(
                QRectF(point.x() - size / 2, point.y() - size / 2, size, size),
                point_pen,
                QColor("#62e8c2"),
            )
            marker.setZValue(4)
            self.items_drawn.append(marker)
        if not self.show_boxes:
            return
        for i, b in enumerate(self.boxes):
            color = QColor("#ff6378" if b.class_id is None else self.colors[b.class_id])
            pen = QPen(QColor("#ffffff") if i == self.selection else color, 2)
            pen.setCosmetic(True)
            rect = self.scene().addRect(
                QRectF(b.x1, b.y1, b.x2 - b.x1, b.y2 - b.y1), pen
            )
            rect.setZValue(1)
            self.items_drawn.append(rect)
            if self.show_labels:
                name = "Chưa gán" if b.class_id is None else self.names[b.class_id]
                text = self.scene().addSimpleText(f"{i + 1} · {name}")
                text.setBrush(color)
                text.setScale(1 / scale)
                text.setPos(b.x1, b.y1)
                text.setZValue(2)
                self.items_drawn.append(text)
            if i == self.selection and self.mode == "Edit":
                for x, y in [(b.x1, b.y1), (b.x2, b.y1), (b.x1, b.y2), (b.x2, b.y2)]:
                    size = 7 / scale
                    h = self.scene().addRect(
                        QRectF(x - size / 2, y - size / 2, size, size),
                        pen,
                        QColor("#ffffff"),
                    )
                    h.setZValue(3)
                    self.items_drawn.append(h)
        if self.preview:
            pen = QPen(QColor("#62e8c2"), 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self.items_drawn.append(self.scene().addRect(self.preview, pen))

    def mousePressEvent(self, event):
        if self.mode == "Pan" or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        if not self.w:
            return
        p = self.point(event.position().toPoint())
        self.start = p
        self.original = deepcopy(self.boxes)
        self.handle = None
        if self.mode == "Draw":
            self.preview = QRectF(p, p)
            return
        tolerance = 10 / max(0.001, self.transform().m11())
        if self.mode == "Edit" and 0 <= self.selection < len(self.boxes):
            b = self.boxes[self.selection]
            for corner, (x, y) in enumerate(
                [(b.x1, b.y1), (b.x2, b.y1), (b.x1, b.y2), (b.x2, b.y2)]
            ):
                if abs(p.x() - x) <= tolerance and abs(p.y() - y) <= tolerance:
                    self.handle = corner
                    break
        if self.handle is None:
            hits = [
                i
                for i, b in enumerate(self.boxes)
                if b.x1 <= p.x() <= b.x2 and b.y1 <= p.y() <= b.y2
            ]
            if (
                self.mode == "Edit"
                and self.selection in hits
                and not (event.modifiers() & Qt.KeyboardModifier.AltModifier)
            ):
                pass  # Preserve the explicit selection when editing overlapping boxes.
            elif (
                event.modifiers() & Qt.KeyboardModifier.AltModifier
                and self.selection in hits
            ):
                self.selection = hits[(hits.index(self.selection) - 1) % len(hits)]
            else:
                self.selection = hits[-1] if hits else -1
        self.selected.emit(self.selection)
        self.render_boxes()

    def mouseMoveEvent(self, event):
        if self.mode == "Pan":
            return super().mouseMoveEvent(event)
        if self.start is None:
            return
        p = self.point(event.position().toPoint())
        if self.mode == "Draw":
            self.preview = QRectF(self.start, p).normalized()
        elif self.mode == "Edit" and self.selection >= 0:
            b = deepcopy(self.original[self.selection])
            if self.handle is None:
                b = b.moved(
                    p.x() - self.start.x(), p.y() - self.start.y(), self.w, self.h
                )
            else:
                if self.handle in (0, 2):
                    b.x1 = min(p.x(), b.x2 - 0.01)
                else:
                    b.x2 = max(p.x(), b.x1 + 0.01)
                if self.handle in (0, 1):
                    b.y1 = min(p.y(), b.y2 - 0.01)
                else:
                    b.y2 = max(p.y(), b.y1 + 0.01)
            self.boxes[self.selection] = b
        self.render_boxes()

    def mouseReleaseEvent(self, event):
        if self.mode == "Pan":
            return super().mouseReleaseEvent(event)
        if self.start is None or event.button() != Qt.MouseButton.LeftButton:
            return
        if self.mode == "Draw":
            p = self.point(event.position().toPoint())
            r = QRectF(self.start, p).normalized()
            threshold = 3 / max(0.001, self.transform().m11())
            is_click = (
                abs(p.x() - self.start.x()) <= threshold
                and abs(p.y() - self.start.y()) <= threshold
            )
            if is_click:
                self.draft_points.append(self.start)
                if len(self.draft_points) == 4:
                    xs = [point.x() for point in self.draft_points]
                    ys = [point.y() for point in self.draft_points]
                    left, right = min(xs), max(xs)
                    top, bottom = min(ys), max(ys)
                    if right - left >= 1 and bottom - top >= 1:
                        self.boxes.append(
                            Box(self.active_class, left, top, right, bottom)
                        )
                        self.selection = len(self.boxes) - 1
                    self.draft_points = []
            elif r.width() >= 1 and r.height() >= 1:
                self.draft_points = []
                self.boxes.append(
                    Box(self.active_class, r.left(), r.top(), r.right(), r.bottom())
                )
                self.selection = len(self.boxes) - 1
        self.preview = None
        self.start = None
        if self.original != self.boxes:
            self.edited.emit(self.original)
        self.selected.emit(self.selection)
        self.render_boxes()

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        if self.grid and self.w:
            pen = QPen(QColor("#526375"), 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            # Background grid is visible around transparent image areas; foreground grid below handles opaque images.

    def drawForeground(self, painter, rect):
        if self.grid and self.w:
            pen = QPen(QColor(180, 200, 220, 50), 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            step = max(20, int(80 / max(0.001, self.transform().m11())))
            for x in range(0, self.w, step):
                painter.drawLine(x, 0, x, self.h)
            for y in range(0, self.h, step):
                painter.drawLine(0, y, self.w, y)
