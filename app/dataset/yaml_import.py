"""Read local YOLO dataset YAML without executing download directives."""

from pathlib import Path
import yaml
from app.core.model import class_names
from app.dataset.images import EXTS, scan


def label_path(image):
    parts = list(image.parts)
    for i in range(len(parts) - 2, -1, -1):
        if parts[i].lower() == "images":
            parts[i] = "labels"
            return Path(*parts).with_suffix(".txt")
    return image.with_suffix(".txt")


def read_dataset(path):
    path = Path(path).resolve()
    config = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict):
        raise ValueError("YAML phải chứa cấu hình dataset YOLO.")
    names = config.get("names")
    if isinstance(names, dict):
        converted = {int(k): v for k, v in names.items()}
        if len(converted) != len(names) or sorted(converted) != list(range(len(names))):
            raise ValueError("YOLO names IDs phải liên tục từ 0.")
        names = [converted[i] for i in range(len(converted))]
    if not isinstance(names, list):
        raise ValueError("YAML cần names là danh sách hoặc ánh xạ ID → tên class.")
    names = class_names(names)
    if "nc" in config and config["nc"] != len(names):
        raise ValueError("nc không khớp số class trong names.")
    root_value = config.get("path") or "."
    if not isinstance(root_value, str):
        raise ValueError("path phải là đường dẫn thư mục.")
    root = (path.parent / root_value).resolve()
    entries = []
    seen = {}
    for key in ("train", "val", "valid", "test", "unassigned"):
        value = config.get(key)
        if value is None or value == "":
            continue
        sources = value if isinstance(value, list) else [value]
        split = "valid" if key == "val" else key
        for source in sources:
            if not isinstance(source, str) or not source.strip():
                raise ValueError(f"{key}: cần đường dẫn hoặc danh sách đường dẫn.")
            location = (root / source).resolve()
            if location.is_dir():
                files = scan(location)
            elif location.is_file() and location.suffix.lower() == ".txt":
                files = [
                    (location.parent / line.strip()).resolve()
                    for line in location.read_text(encoding="utf-8-sig").splitlines()
                    if line.strip()
                ]
            elif location.is_file() and location.suffix.lower() in EXTS:
                files = [location]
            else:
                raise ValueError(f"Không tìm thấy đường dẫn ảnh {key}: {location}")
            if not files:
                raise ValueError(f"Không tìm thấy ảnh trong {location}")
            for image in files:
                image = image.resolve()
                if not image.is_file() or image.suffix.lower() not in EXTS:
                    raise ValueError(f"Ảnh không tồn tại hoặc không hỗ trợ: {image}")
                if image in seen:
                    if seen[image] != split:
                        raise ValueError(f"Ảnh xuất hiện ở nhiều tập: {image}")
                    continue
                seen[image] = split
                entries.append((image, label_path(image), split))
    if not entries:
        raise ValueError("YAML cần đường dẫn ảnh trong train, val, valid hoặc test.")
    return names, entries
