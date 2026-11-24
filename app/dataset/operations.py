import csv, hashlib, json, random, shutil
from pathlib import Path
from collections import Counter, defaultdict
from PIL import Image
import yaml
from app.formats import yolo, coco
from app.services.storage import safe_child, write_json


def statistics(project):
    records = project.data["images"]
    objects = Counter()
    per_image = Counter()
    for r in records:
        counts = Counter(b["class_id"] for b in r["boxes"])
        objects.update(counts)
        per_image.update(counts.keys())
    return {
        "total_images": len(records),
        "labeled_images": sum(
            bool(r["boxes"]) or r["status"] == "Confirmed Empty" for r in records
        ),
        "unlabeled_images": sum(r["status"] == "Unlabeled" for r in records),
        "reviewed_images": sum(r["status"] == "Reviewed" for r in records),
        "total_annotations": sum(objects.values()),
        "number_of_classes": len(project.data["classes"]),
        "multiple_objects": sum(len(r["boxes"]) > 1 for r in records),
        "multiple_classes": sum(
            len({b["class_id"] for b in r["boxes"]}) > 1 for r in records
        ),
        "splits": dict(Counter(r["split"] for r in records)),
        "statuses": dict(Counter(r["status"] for r in records)),
        "classes": [
            {"id": i, "name": n, "objects": objects[i], "images": per_image[i]}
            for i, n in enumerate(project.data["classes"])
        ],
    }


def report_csv(project, path):
    stats = statistics(project)
    with open(path, "x", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Metric", "Value"])
        for k, v in stats.items():
            if k != "classes":
                writer.writerow(
                    [k, json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v]
                )
        writer.writerow([])
        writer.writerow(["Class ID", "Class name", "Objects", "Images"])
        for r in stats["classes"]:
            writer.writerow([r["id"], r["name"], r["objects"], r["images"]])


def audit_folder(image_root, label_root):
    from app.dataset.images import scan

    images = scan(image_root)
    stem_groups = defaultdict(list)
    for p in images:
        stem_groups[str(p.relative_to(image_root).with_suffix("")).casefold()].append(p)
    issues = []
    expected = set()
    for group in stem_groups.values():
        if len(group) > 1:
            issues.append("Trùng tên nhãn: " + ", ".join(str(p) for p in group))
    for p in images:
        rel = p.relative_to(image_root).with_suffix(".txt")
        expected.add(rel.as_posix())
        if not (Path(label_root) / rel).exists():
            issues.append("Thiếu nhãn: " + str(rel))
    for p in Path(label_root).rglob("*.txt"):
        if p.relative_to(label_root).as_posix() not in expected:
            issues.append("Nhãn không có ảnh: " + str(p))
    return issues


def validate(project, duplicates=True):
    issues = []
    exact = {}
    hashes = []
    names = defaultdict(list)
    for r in project.data["images"]:
        names[Path(r["name"]).stem.casefold()].append(r["name"])
        try:
            path = safe_child(project.root, r["path"])
            with Image.open(path) as im:
                im.load()
                if im.size != (r["width"], r["height"]):
                    raise ValueError("Độ phân giải đã thay đổi")
                small = im.convert("L").resize((9, 8))
                pixels = list(small.tobytes())
                dh = sum(
                    (pixels[y * 9 + x] > pixels[y * 9 + x + 1]) << (y * 8 + x)
                    for y in range(8)
                    for x in range(8)
                )
            for b in project.boxes(r):
                b.validate(r["width"], r["height"], len(project.data["classes"]))
            if not r["boxes"] and r["status"] not in (
                "Unlabeled",
                "In Progress",
                "Confirmed Empty",
            ):
                raise ValueError("Ảnh rỗng chưa xác nhận")
            if r["boxes"] and r["status"] == "Confirmed Empty":
                raise ValueError("Ảnh rỗng vẫn còn box")
            if duplicates:
                digest = hashlib.sha256()
                with path.open("rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        digest.update(chunk)
                key = digest.hexdigest()
                if key in exact:
                    issues.append(
                        f"Ảnh trùng: {exact[key]['name']} ↔ {r['name']} ({exact[key]['split']}/{r['split']})"
                    )
                else:
                    exact[key] = r
                for old, oldhash in hashes:
                    if old["split"] != r["split"] and (dh ^ oldhash).bit_count() <= 4:
                        issues.append(
                            f"Nghi gần giống giữa các tập (cần xem lại): {old['name']} ↔ {r['name']}"
                        )
                        break
                hashes.append((r, dh))
        except Exception as e:
            issues.append(f"{r['name']}: {e}")
    for name, group in names.items():
        if len(group) > 1:
            issues.append(
                f"Trùng stem nguồn {name} ({len(group)} ảnh); file nội bộ đã dùng ID riêng."
            )
    return issues


def split_plan(project, ratios, seed):
    if len(ratios) != 3 or any(v < 0 for v in ratios) or abs(sum(ratios) - 1) > 1e-6:
        raise ValueError("Tỷ lệ train, valid, test phải cộng thành 1.")
    ids = [r["id"] for r in project.data["images"]]
    random.Random(seed).shuffle(ids)
    a = int(len(ids) * ratios[0])
    b = a + int(len(ids) * ratios[1])
    return {
        key: "train" if i < a else "valid" if i < b else "test"
        for i, key in enumerate(ids)
    }


def export_dataset(project, destination, fmt="yolo", plan=None):
    """Stage into sibling temp dir; final rename only after every image succeeds."""
    import tempfile

    dest = Path(destination).resolve()
    if dest.exists():
        raise ValueError("Thư mục xuất phải chưa tồn tại.")
    if dest.is_relative_to(project.root):
        raise ValueError("Xuất ra ngoài project để tránh lẫn dữ liệu.")
    records = project.data["images"]
    if not records:
        raise ValueError("Project chưa có ảnh.")
    pending = [
        r["name"]
        for r in records
        if not r["boxes"] and r["status"] != "Confirmed Empty"
    ]
    if pending:
        raise ValueError(
            f"Còn {len(pending)} ảnh chưa gán nhãn/xác nhận rỗng. Xuất bị chặn, không tạo nhãn rỗng giả."
        )
    if list((project.root / ".drafts").glob("*.json")):
        raise ValueError("Còn bản nháp chưa lưu; xử lý bản nháp trước khi xuất.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".annotation-export-", dir=dest.parent))
    try:
        entries = []
        splits = set()
        for r in records:
            split = plan[r["id"]] if plan else r["split"]
            splits.add(split)
            source = safe_child(project.root, r["path"])
            name = r["id"] + source.suffix
            relative = Path("images") / split / name
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            boxes = project.boxes(r)
            if fmt == "yolo":
                lp = stage / "labels" / split / (r["id"] + ".txt")
                lp.parent.mkdir(parents=True, exist_ok=True)
                lp.write_text(
                    yolo.dumps(
                        boxes, r["width"], r["height"], len(project.data["classes"])
                    ),
                    encoding="utf-8",
                )
            entries.append(
                (
                    {
                        "file_name": relative.as_posix(),
                        "width": r["width"],
                        "height": r["height"],
                    },
                    boxes,
                )
            )
        if fmt == "coco":
            write_json(
                stage / "annotations.json",
                coco.dumps(entries, project.data["classes"]),
                False,
            )
        elif fmt == "yolo":
            config = {
                "names": dict(enumerate(project.data["classes"])),
                "nc": len(project.data["classes"]),
            }
            for s in ("train", "valid", "test"):
                if s in splits:
                    config["val" if s == "valid" else s] = f"images/{s}"
            if "unassigned" in splits:
                config["unassigned"] = "images/unassigned"
            (stage / "data.yaml").write_text(
                yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        else:
            raise ValueError("Định dạng chưa hỗ trợ")
        write_json(
            stage / "source_map.json", {r["id"]: r["name"] for r in records}, False
        )
        stage.rename(dest)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return dest
