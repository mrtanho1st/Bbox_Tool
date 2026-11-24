from collections import defaultdict
from app.core.model import Box, class_names


def loads(data):
    categories = sorted(data["categories"], key=lambda c: c["id"])
    if len({c["id"] for c in categories}) != len(categories):
        raise ValueError("Trùng COCO category ID")
    names = class_names([c["name"] for c in categories])
    mapping = {c["id"]: i for i, c in enumerate(categories)}
    images = {}
    annotations = defaultdict(list)
    ids = set()
    for im in data["images"]:
        if im["id"] in images:
            raise ValueError("Trùng COCO image ID")
        images[im["id"]] = im
    for a in data["annotations"]:
        if a["id"] in ids:
            raise ValueError("Trùng COCO annotation ID")
        ids.add(a["id"])
        if a.get("iscrowd", 0):
            raise ValueError("Chưa hỗ trợ iscrowd=1; không tự bỏ metadata.")
        if a["image_id"] not in images or a["category_id"] not in mapping:
            raise ValueError("COCO tham chiếu ID không tồn tại")
        im = images[a["image_id"]]
        x, y, w, h = a["bbox"]
        b = Box(mapping[a["category_id"]], x, y, x + w, y + h)
        b.validate(im["width"], im["height"], len(names))
        annotations[a["image_id"]].append(b)
    return names, [(im, annotations[key]) for key, im in images.items()]


def dumps(entries, classes):
    result = {
        "images": [],
        "annotations": [],
        "categories": [{"id": i + 1, "name": n} for i, n in enumerate(classes)],
    }
    aid = 1
    for iid, (record, boxes) in enumerate(entries, 1):
        result["images"].append(
            {
                "id": iid,
                "file_name": record["file_name"],
                "width": record["width"],
                "height": record["height"],
            }
        )
        for b in boxes:
            b.validate(record["width"], record["height"], len(classes))
            w = b.x2 - b.x1
            h = b.y2 - b.y1
            result["annotations"].append(
                {
                    "id": aid,
                    "image_id": iid,
                    "category_id": b.class_id + 1,
                    "bbox": [b.x1, b.y1, w, h],
                    "area": w * h,
                    "iscrowd": 0,
                }
            )
            aid += 1
    return result
