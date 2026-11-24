from pathlib import Path
from PIL import Image, ImageOps
from app.core.model import Box

EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    EXTS |= {".heic", ".heif"}
except ImportError:
    pass


def scan(folder):
    return sorted(
        p for p in Path(folder).rglob("*") if p.is_file() and p.suffix.lower() in EXTS
    )


def orient_box(b, w, h, orientation):
    def point(x, y):
        return {
            1: (x, y),
            2: (w - x, y),
            3: (w - x, h - y),
            4: (x, h - y),
            5: (y, x),
            6: (h - y, x),
            7: (h - y, w - x),
            8: (y, w - x),
        }.get(orientation, (x, y))

    points = [
        point(x, y) for x, y in [(b.x1, b.y1), (b.x2, b.y1), (b.x1, b.y2), (b.x2, b.y2)]
    ]
    return Box(
        b.class_id,
        min(p[0] for p in points),
        min(p[1] for p in points),
        max(p[0] for p in points),
        max(p[1] for p in points),
    )


def inspect(path):
    with Image.open(path) as im:
        im.load()
        return im.size, int(im.getexif().get(274, 1))


def normalized_copy(source, target):
    import shutil

    with Image.open(source) as im:
        orientation = int(im.getexif().get(274, 1))
        if orientation not in (0, 1):
            target = target.with_suffix(".png")
            ImageOps.exif_transpose(im).convert("RGB").save(target)
        else:
            shutil.copy2(source, target)
    return target
