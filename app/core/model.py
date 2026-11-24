"""Pure annotation model; all coordinates are original image pixels."""

from dataclasses import dataclass, asdict, replace
from copy import deepcopy
import math

STATUSES = ["Unlabeled", "In Progress", "Completed", "Reviewed", "Confirmed Empty"]


@dataclass
class Box:
    class_id: int | None
    x1: float
    y1: float
    x2: float
    y2: float

    def validate(self, width, height, count, allow_unassigned=False):
        if not all(math.isfinite(v) for v in (self.x1, self.y1, self.x2, self.y2)):
            raise ValueError("Tọa độ không hữu hạn.")
        if not (0 <= self.x1 < self.x2 <= width and 0 <= self.y1 < self.y2 <= height):
            raise ValueError("Box rỗng hoặc nằm ngoài ảnh.")
        if self.class_id is None and allow_unassigned:
            return
        if type(self.class_id) is not int or not 0 <= self.class_id < count:
            raise ValueError("Class ID không hợp lệ hoặc chưa gán class.")

    def dict(self):
        return asdict(self)

    def moved(self, dx, dy, w, h):
        dx = max(-self.x1, min(dx, w - self.x2))
        dy = max(-self.y1, min(dy, h - self.y2))
        return replace(
            self, x1=self.x1 + dx, x2=self.x2 + dx, y1=self.y1 + dy, y2=self.y2 + dy
        )


class History:
    def __init__(self):
        self.past = []
        self.future = []

    def push(self, boxes):
        self.past.append(deepcopy(boxes))
        self.past = self.past[-100:]
        self.future = []

    def undo(self, boxes):
        if not self.past:
            return boxes
        self.future.append(deepcopy(boxes))
        return self.past.pop()

    def redo(self, boxes):
        if not self.future:
            return boxes
        self.past.append(deepcopy(boxes))
        return self.future.pop()


def class_names(names):
    names = [str(n).strip() for n in names]
    if not names or any(not n for n in names) or len(set(names)) != len(names):
        raise ValueError("Cần ít nhất một class; tên không rỗng và không trùng.")
    return names


def color(index):
    import colorsys

    return "#%02x%02x%02x" % tuple(
        int(v * 255)
        for v in colorsys.hsv_to_rgb((index * 0.61803398875) % 1, 0.65, 0.95)
    )
