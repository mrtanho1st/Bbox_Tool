from app.core.model import Box


def loads(text, width, height, count):
    boxes = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            fields = line.split()
            if len(fields) != 5:
                raise ValueError("Cần đúng 5 cột bounding box")
            cls = int(fields[0])
            x, y, w, h = map(float, fields[1:])
            b = Box(
                cls,
                (x - w / 2) * width,
                (y - h / 2) * height,
                (x + w / 2) * width,
                (y + h / 2) * height,
            )
            # Permit rounding noise at the borders, not genuinely invalid boxes.
            for attr, limit in [
                ("x1", width),
                ("x2", width),
                ("y1", height),
                ("y2", height),
            ]:
                v = getattr(b, attr)
                if -1e-5 * limit <= v < 0:
                    setattr(b, attr, 0.0)
                if limit < v <= limit * (1 + 1e-5):
                    setattr(b, attr, float(limit))
            b.validate(width, height, count)
            boxes.append(b)
        except (ValueError, OverflowError) as e:
            raise ValueError(f"Dòng YOLO {line_no}: {e}") from e
    return boxes


def dumps(boxes, width, height, count):
    lines = []
    for b in boxes:
        b.validate(width, height, count)
        lines.append(
            f"{b.class_id} {(b.x1 + b.x2) / 2 / width:.9f} {(b.y1 + b.y2) / 2 / height:.9f} {(b.x2 - b.x1) / width:.9f} {(b.y2 - b.y1) / height:.9f}"
        )
    return "\n".join(lines) + ("\n" if lines else "")
