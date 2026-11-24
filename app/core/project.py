"""Portable projects. External datasets are only read; edits live in project copies."""

from pathlib import Path
from copy import deepcopy
import uuid, shutil
from tempfile import TemporaryDirectory
from app.services.storage import read_json, write_json, now, safe_child
from app.core.model import Box, class_names, color, STATUSES
from app.dataset.images import scan, inspect, normalized_copy, orient_box
from app.formats import yolo, coco


class Project:
    def __init__(self, path, data):
        self.path = Path(path).resolve()
        self.root = self.path.parent
        self.data = data
        self.loaded_bytes = self.path.read_bytes() if self.path.exists() else None

    @classmethod
    def create(cls, folder, name, names, description=""):
        folder = Path(folder).resolve()
        if folder.exists() and any(folder.iterdir()):
            raise ValueError("Chọn thư mục project mới hoặc rỗng để tránh ghi đè.")
        folder.mkdir(parents=True, exist_ok=True)
        names = class_names(names)
        p = cls(
            folder / "project.json",
            {
                "schema": 1,
                "id": uuid.uuid4().hex,
                "name": name.strip() or "Untitled",
                "description": description,
                "created": now(),
                "updated": now(),
                "classes": names,
                "colors": [color(i) for i in range(len(names))],
                "images": [],
                "format": "yolo",
                "annotation_type": "bounding_box",
            },
        )
        p.commit()
        return p

    @classmethod
    def open(cls, path):
        data = read_json(path)
        if data.get("schema") != 1:
            raise ValueError("Schema chưa được hỗ trợ.")
        class_names(data["classes"])
        p = cls(path, data)
        seen = set()
        for r in data["images"]:
            if r["id"] in seen:
                raise ValueError("Trùng image ID")
            seen.add(r["id"])
            safe_child(p.root, r["path"])
            if r["status"] not in STATUSES:
                raise ValueError("Trạng thái ảnh không hợp lệ")
            for b in p.boxes(r):
                b.validate(r["width"], r["height"], len(data["classes"]))
        return p

    def commit(self):
        if (
            self.path.exists()
            and self.loaded_bytes is not None
            and self.path.read_bytes() != self.loaded_bytes
        ):
            raise ValueError(
                "Project đã được sửa bởi phiên khác. Hãy mở lại; bản nháp vẫn được giữ."
            )
        updated = deepcopy(self.data)
        updated["updated"] = now()
        write_json(self.path, updated)
        self.data = updated
        self.loaded_bytes = self.path.read_bytes()

    def boxes(self, record):
        return [Box(**b) for b in record.get("boxes", [])]

    def draft_path(self, r):
        return self.root / ".drafts" / (r["id"] + ".json")

    def draft(self, r, boxes, status):
        write_json(
            self.draft_path(r),
            {
                "classes": self.data["classes"],
                "boxes": [b.dict() for b in boxes],
                "status": status,
            },
            backup=False,
        )

    def recover(self, r):
        path = self.draft_path(r)
        if not path.exists():
            return None
        d = read_json(path)
        if d["classes"] != self.data["classes"]:
            raise ValueError("Class của bản nháp khác cấu hình hiện tại.")
        boxes = [Box(**b) for b in d["boxes"]]
        for b in boxes:
            b.validate(r["width"], r["height"], len(d["classes"]), True)
        if d["status"] not in STATUSES:
            raise ValueError("Trạng thái bản nháp không hợp lệ")
        return boxes, d["status"]

    def discard_draft(self, r):
        self.draft_path(r).unlink(missing_ok=True)

    def save(self, record, boxes, status):
        if status not in STATUSES:
            raise ValueError("Trạng thái không hợp lệ")
        if not boxes and status != "Confirmed Empty":
            raise ValueError(
                "Ảnh không có box: chọn Confirmed Empty để xác nhận rõ ràng."
            )
        if boxes and status == "Confirmed Empty":
            raise ValueError("Ảnh còn box, không thể đánh dấu rỗng.")
        for b in boxes:
            b.validate(record["width"], record["height"], len(self.data["classes"]))
        before = deepcopy(self.data)
        target = next(r for r in self.data["images"] if r["id"] == record["id"])
        target["boxes"] = [b.dict() for b in boxes]
        target["status"] = status
        try:
            self.commit()
        except Exception:
            self.data = before
            raise
        self.discard_draft(record)

    def delete_image(self, record):
        """Delete a project image, annotations and draft; roll back failed commits."""
        target = next(r for r in self.data["images"] if r["id"] == record["id"])
        image = safe_child(self.root, target["path"])
        draft = safe_child(self.root, self.draft_path(target))
        before = deepcopy(self.data)
        with TemporaryDirectory(prefix=".delete-", dir=self.root,
                                ignore_cleanup_errors=True) as directory:
            moved = []
            try:
                for i, path in enumerate((image, draft)):
                    if path.exists():
                        staged = Path(directory) / str(i)
                        path.rename(staged)
                        moved.append((path, staged))
                self.data["images"] = [
                    r for r in self.data["images"] if r["id"] != target["id"]
                ]
                self.commit()
            except Exception:
                self.data = before
                for path, staged in reversed(moved):
                    staged.rename(path)
                raise

    def import_yaml(self, path):
        from app.dataset.yaml_import import read_dataset

        names, entries = read_dataset(path)
        if names != self.data["classes"]:
            raise ValueError("Classes trong YAML khác project.")
        return self.import_files(
            [image for image, label, split in entries],
            label_paths=[label for image, label, split in entries],
            splits=[split for image, label, split in entries],
        )

    def import_files(self, files, root=None, label_root=None, coco_rows=None,
                     label_paths=None, splits=None):
        """All records committed together; corrupted input aborts and rolls back new copies."""
        files = [Path(p).resolve() for p in files]
        root = Path(root).resolve() if root else None
        label_root = Path(label_root).resolve() if label_root else None
        batch = uuid.uuid4().hex[:12]
        directory = self.root / "images" / batch
        directory.mkdir(parents=True)
        records = []
        before = deepcopy(self.data)
        try:
            for idx, source in enumerate(files):
                (w, h), orientation = inspect(source)
                rel = source.relative_to(root) if root else Path(source.name)
                boxes = []
                status = "Unlabeled"
                if coco_rows is not None:
                    im, boxes = coco_rows[idx]
                    if (im["width"], im["height"]) != (w, h):
                        raise ValueError(f"COCO size khác ảnh: {source.name}")
                    status = "In Progress" if boxes else "Confirmed Empty"
                elif label_root or label_paths is not None:
                    lp = (Path(label_paths[idx]) if label_paths is not None
                          else safe_child(label_root, rel.with_suffix(".txt")))
                    if lp.exists():
                        boxes = yolo.loads(
                            lp.read_text(encoding="utf-8-sig"),
                            w,
                            h,
                            len(self.data["classes"]),
                        )
                        status = "In Progress" if boxes else "Unlabeled"
                # ID in physical filename avoids duplicate stems and case collisions on Windows.
                ident = uuid.uuid4().hex
                target = normalized_copy(
                    source, directory / (ident + source.suffix.lower())
                )
                if orientation not in (0, 1):
                    boxes = [orient_box(b, w, h, orientation) for b in boxes]
                nw, nh = (h, w) if orientation in (5, 6, 7, 8) else (w, h)
                split = next(
                    (
                        s
                        for s in rel.parts[:-1]
                        if s in ("train", "val", "valid", "test")
                    ),
                    "unassigned",
                )
                if split == "val":
                    split = "valid"
                if splits is not None:
                    split = splits[idx]
                records.append(
                    {
                        "id": ident,
                        "path": str(target.relative_to(self.root)).replace("\\", "/"),
                        "name": str(rel),
                        "width": nw,
                        "height": nh,
                        "split": split,
                        "status": status,
                        "boxes": [b.dict() for b in boxes],
                    }
                )
            self.data["images"].extend(records)
            self.commit()
        except Exception:
            self.data = before
            shutil.rmtree(directory)
            raise
        return len(records)

    def import_folder(self, folder, label_root=None):
        files = scan(folder)
        if not files:
            raise ValueError("Không tìm thấy ảnh hỗ trợ.")
        return self.import_files(files, folder, label_root)

    def import_coco(self, json_path, image_root):
        names, rows = coco.loads(read_json(json_path))
        if names != self.data["classes"]:
            raise ValueError(
                "Class COCO khác project. Tạo project với class COCO trước."
            )
        files = [safe_child(image_root, im["file_name"]) for im, b in rows]
        return self.import_files(files, image_root, coco_rows=rows)

    def migrate_classes(self, names, old_to_new, colors=None):
        names = class_names(names)
        if list((self.root / ".drafts").glob("*.json")):
            raise ValueError("Lưu hoặc xử lý các bản nháp trước khi đổi class.")
        before = deepcopy(self.data)
        for r in self.data["images"]:
            for b in r["boxes"]:
                target = old_to_new.get(b["class_id"])
                if target is None:
                    raise ValueError("Không được xóa class còn được sử dụng.")
                if not 0 <= target < len(names):
                    raise ValueError("Ánh xạ class không hợp lệ")
        self.data["classes"] = names
        self.data["colors"] = colors or [color(i) for i in range(len(names))]
        for r in self.data["images"]:
            for b in r["boxes"]:
                b["class_id"] = old_to_new[b["class_id"]]
        try:
            self.commit()
        except Exception:
            self.data = before
            raise

    def duplicate(self, destination):
        dest = Path(destination).resolve()
        if dest == self.root or dest.is_relative_to(self.root):
            raise ValueError("Bản sao phải nằm ngoài project gốc.")
        if dest.exists():
            raise ValueError("Thư mục đích phải chưa tồn tại.")
        shutil.copytree(
            self.root, dest, ignore=shutil.ignore_patterns(".backups", ".drafts")
        )
        p = Project.open(dest / "project.json")
        p.data["id"] = uuid.uuid4().hex
        p.data["name"] += " (copy)"
        p.commit()
        return p
