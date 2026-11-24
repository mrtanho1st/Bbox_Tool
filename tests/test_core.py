from copy import deepcopy
import json
import pytest
from PIL import Image
from app.core.model import Box, History
from app.core.project import Project
from app.formats import yolo, coco
from app.services.storage import atomic_text, write_json, safe_child
from app.dataset.images import orient_box
from app.dataset.operations import (
    statistics,
    validate,
    export_dataset,
    split_plan,
    audit_folder,
    report_csv,
)


@pytest.mark.parametrize(
    "box",
    [
        Box(0, 0, 0, 0, 3),
        Box(0, -1, 0, 2, 3),
        Box(2, 0, 0, 2, 3),
        Box(None, 0, 0, 2, 3),
        Box(0, 0, 0, float("nan"), 3),
    ],
)
def test_invalid_boxes(box):
    with pytest.raises(ValueError):
        box.validate(100, 100, 2)


def test_delete_image_removes_annotations_and_draft(project):
    record = project.data["images"][0]
    image = project.root / record["path"]
    project.save(record, [Box(0, 1, 1, 10, 10)], "Completed")
    project.draft(record, [Box(1, 2, 2, 20, 20)], "In Progress")
    project.delete_image(record)
    assert not image.exists()
    assert not project.draft_path(record).exists()
    assert Project.open(project.path).data["images"] == []
    assert len(list((project.root.parent / "ảnh đầu vào").glob("*.png"))) == 1


def test_delete_image_rolls_back_failed_commit(project, monkeypatch):
    record = project.data["images"][0]
    image = project.root / record["path"]
    project.draft(record, [], "Unlabeled")
    before = deepcopy(project.data)

    def fail():
        raise OSError("Cannot save project")

    monkeypatch.setattr(project, "commit", fail)
    with pytest.raises(OSError):
        project.delete_image(record)
    assert project.data == before
    assert image.exists()
    assert project.draft_path(record).exists()
    assert Project.open(project.path).data == before


def test_yolo_roundtrip():
    boxes = [Box(0, 0, 0, 200, 100), Box(1, 23.1, 4.2, 58.3, 90.5)]
    actual = yolo.loads(yolo.dumps(boxes, 200, 100, 2), 200, 100, 2)
    for a, b in zip(actual, boxes):
        assert a.class_id == b.class_id
        assert [a.x1, a.y1, a.x2, a.y2] == pytest.approx(
            [b.x1, b.y1, b.x2, b.y2], abs=1e-6
        )


@pytest.mark.parametrize(
    "text",
    [
        "2 .5 .5 .2 .2",
        "0 nan .5 .2 .2",
        "0 .5 .5 0 .2",
        "0 .5 .5 .2",
        "x .5 .5 .2 .2",
        "0 2 2 .2 .2",
        "0 .5 .5 -.2 .2",
    ],
)
def test_yolo_strict(text):
    with pytest.raises(ValueError):
        yolo.loads(text, 100, 100, 2)


def test_create_independent_and_reopen(tmp_path):
    a = Project.create(tmp_path / "a", "A", ["cat"])
    b = Project.create(tmp_path / "b", "B", ["bus", "truck"])
    assert Project.open(a.path).data["classes"] == ["cat"] and b.data["classes"] == [
        "bus",
        "truck",
    ]
    with pytest.raises(ValueError):
        Project.create(tmp_path / "a", "Overwrite", ["x"])


def test_no_write_on_view(project):
    before = project.path.read_bytes()
    p = Project.open(project.path)
    assert p.boxes(p.data["images"][0]) == [] and project.path.read_bytes() == before
    assert not list(project.root.rglob("*.txt"))


def test_save_guard_and_draft_recovery(project):
    r = project.data["images"][0]
    before = project.path.read_bytes()
    with pytest.raises(ValueError):
        project.save(r, [], "Completed")
    with pytest.raises(ValueError):
        project.save(r, [Box(None, 0, 0, 10, 10)], "In Progress")
    assert before == project.path.read_bytes()
    project.draft(r, [Box(None, 0, 0, 10, 10)], "In Progress")
    p = Project.open(project.path)
    boxes, status = p.recover(r)
    assert boxes[0].class_id is None and status == "In Progress"
    p.save(r, [], "Confirmed Empty")
    assert p.recover(r) is None


def test_migrate_backup_recover(project):
    r = project.data["images"][0]
    project.save(r, [Box(0, 0, 0, 10, 10), Box(1, 0, 0, 20, 20)], "Reviewed")
    before = project.path.read_bytes()
    with pytest.raises(ValueError):
        project.migrate_classes(["car"], {0: 0})
    assert before == project.path.read_bytes()
    project.migrate_classes(["bus", "car", "truck"], {0: 1, 1: 0})
    assert [b["class_id"] for b in project.data["images"][0]["boxes"]] == [1, 0]
    assert before in [f.read_bytes() for f in (project.root / ".backups").glob("*")]


def test_concurrent_write_refused(project):
    other = Project.open(project.path)
    other.data["name"] = "elsewhere"
    other.commit()
    with pytest.raises(ValueError):
        project.commit()
    assert Project.open(project.path).data["name"] == "elsewhere"


def test_atomic_failure_keeps_original(tmp_path, monkeypatch):
    import app.services.storage as storage

    path = tmp_path / "file"
    path.write_text("old")

    def fail(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(storage.os, "replace", fail)
    with pytest.raises(OSError):
        atomic_text(path, "new")
    assert path.read_text() == "old" and list((tmp_path / ".backups").glob("*"))


def test_coco_arbitrary_ids():
    data = {
        "categories": [{"id": 90, "name": "bus"}, {"id": 10, "name": "car"}],
        "images": [{"id": 45, "file_name": "a.png", "width": 100, "height": 80}],
        "annotations": [
            {"id": 70, "image_id": 45, "category_id": 90, "bbox": [1, 2, 20, 30]}
        ],
    }
    names, rows = coco.loads(data)
    assert names == ["car", "bus"] and rows[0][1][0].class_id == 1
    out = coco.dumps(rows, names)
    assert out["annotations"][0]["category_id"] == 2
    n, r = coco.loads(out)
    assert r[0][1][0] == rows[0][1][0]


def test_import_yolo_source_unchanged(tmp_path):
    images = tmp_path / "source" / "images" / "train"
    images.mkdir(parents=True)
    labels = tmp_path / "source" / "labels" / "train"
    labels.mkdir(parents=True)
    Image.new("RGB", (200, 100)).save(images / "a.jpg")
    (labels / "a.txt").write_text("1 .5 .5 .5 .5\n")
    original = (labels / "a.txt").read_bytes()
    p = Project.create(tmp_path / "project", "P", ["a", "b"])
    p.import_folder(images.parent, labels.parent)
    r = p.data["images"][0]
    assert r["split"] == "train" and r["boxes"][0]["class_id"] == 1
    p.save(r, [Box(0, 1, 2, 3, 4)], "Completed")
    assert (labels / "a.txt").read_bytes() == original


def test_corrupt_input_rolls_back(project, tmp_path):
    source = tmp_path / "bad"
    source.mkdir()
    Image.new("RGB", (10, 10)).save(source / "a.png")
    (source / "z.png").write_text("bad image")
    before = project.path.read_bytes()
    dirs = set((project.root / "images").iterdir())
    with pytest.raises(Exception):
        project.import_folder(source)
    assert (
        project.path.read_bytes() == before
        and set((project.root / "images").iterdir()) == dirs
    )


def test_duplicate_filename_safe(project, tmp_path):
    source = tmp_path / "other"
    source.mkdir()
    Image.new("RGB", (10, 10)).save(source / "same.png")
    Image.new("RGB", (10, 10)).save(source / "same.jpg")
    project.import_folder(source)
    assert len({r["path"] for r in project.data["images"]}) == 3
    assert any("Trùng stem" in s for s in validate(project))


def test_export_and_stats(project, tmp_path):
    r = project.data["images"][0]
    with pytest.raises(ValueError):
        export_dataset(project, tmp_path / "invalid")
    project.save(r, [Box(0, 1, 2, 20, 30), Box(1, 10, 20, 80, 90)], "Completed")
    s = statistics(project)
    assert s["total_annotations"] == 2 and s["multiple_classes"] == 1
    dest = export_dataset(project, tmp_path / "export")
    labels = list(dest.rglob("*.txt"))
    assert len(labels) == 1
    assert len(yolo.loads(labels[0].read_text(), 200, 100, 2)) == 2
    dest2 = export_dataset(project, tmp_path / "coco", "coco")
    names, rows = coco.loads(json.loads((dest2 / "annotations.json").read_text()))
    assert len(rows[0][1]) == 2
    report_csv(project, tmp_path / "report.csv")
    assert (tmp_path / "report.csv").exists()
    with pytest.raises(ValueError):
        export_dataset(project, dest)


def test_export_empty_only_explicit(project, tmp_path):
    project.save(project.data["images"][0], [], "Confirmed Empty")
    dest = export_dataset(project, tmp_path / "empty")
    assert next(dest.rglob("*.txt")).read_text() == ""


def test_split_deterministic_and_no_mutation(project, tmp_path):
    folder = tmp_path / "many"
    folder.mkdir()
    for i in range(12):
        Image.new("RGB", (5, 5)).save(folder / f"{i}.png")
    project.import_folder(folder)
    before = deepcopy(project.data)
    assert (
        split_plan(project, [0.8, 0.1, 0.1], 42)
        == split_plan(project, [0.8, 0.1, 0.1], 42)
        and before == project.data
    )
    with pytest.raises(ValueError):
        split_plan(project, [1, 1, 1], 0)


def test_undo_redo_and_move():
    a = [Box(0, 0, 0, 20, 20)]
    history = History()
    history.push(a)
    b = [a[0].moved(100, 100, 100, 100)]
    assert (
        b[0].x2 == 100
        and b[0].y2 == 100
        and history.undo(b) == a
        and history.redo(a) == b
    )


@pytest.mark.parametrize("orientation", range(1, 9))
def test_exif_corner_bounds(orientation):
    b = orient_box(Box(0, 0, 0, 200, 100), 200, 100, orientation)
    w, h = (100, 200) if orientation >= 5 else (200, 100)
    b.validate(w, h, 1)
    assert b.x2 == w and b.y2 == h


def test_exif_import(project, tmp_path):
    source = tmp_path / "rotated"
    source.mkdir()
    im = Image.new("RGB", (40, 20))
    exif = im.getexif()
    exif[274] = 6
    im.save(source / "a.jpg", exif=exif)
    project.import_folder(source)
    r = project.data["images"][-1]
    assert (r["width"], r["height"]) == (20, 40)
    with Image.open(project.root / r["path"]) as out:
        assert out.size == (20, 40) and out.getexif().get(274, 1) == 1
    with Image.open(source / "a.jpg") as original:
        assert original.size == (40, 20) and original.getexif()[274] == 6


def test_paths_confined(tmp_path):
    with pytest.raises(ValueError):
        safe_child(tmp_path, "../outside")


def test_audit_orphan(tmp_path):
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    labels.mkdir()
    Image.new("RGB", (1, 1)).save(images / "a.png")
    (labels / "orphan.txt").write_text("")
    issues = audit_folder(images, labels)
    assert any("Thiếu" in s for s in issues) and any(
        "không có ảnh" in s for s in issues
    )


def test_duplicate_portable(project, tmp_path):
    p = project.duplicate(tmp_path / "copy")
    assert (
        p.data["id"] != project.data["id"]
        and (p.root / p.data["images"][0]["path"]).exists()
    )
    with pytest.raises(ValueError):
        project.duplicate(project.root / "nested")


def test_import_coco(project, tmp_path):
    source = tmp_path / "coco-source"
    source.mkdir()
    Image.new("RGB", (30, 20)).save(source / "x.png")
    data = {
        "categories": [{"id": 9, "name": "car"}, {"id": 50, "name": "bus"}],
        "images": [{"id": 8, "file_name": "x.png", "width": 30, "height": 20}],
        "annotations": [
            {"id": 1, "image_id": 8, "category_id": 50, "bbox": [1, 2, 5, 6]}
        ],
    }
    path = source / "annotations.json"
    write_json(path, data)
    project.import_coco(path, source)
    assert project.data["images"][-1]["boxes"][0]["class_id"] == 1


def test_many_images_open_without_decoding(project, tmp_path, monkeypatch):
    folder = tmp_path / "many_images"
    folder.mkdir()
    for i in range(256):
        Image.new("RGB", (10, 10)).save(folder / f"{i}.png")
    project.import_folder(folder)

    def forbidden(*args, **kwargs):
        raise AssertionError("Opening a project must not decode the dataset into RAM")

    monkeypatch.setattr(Image, "open", forbidden)
    p = Project.open(project.path)
    assert len(p.data["images"]) == 257


def test_classes_more_than_nine_and_add_rename(project):
    names = [f"object {i}" for i in range(20)]
    project.migrate_classes(names, {0: 0, 1: 1})
    r = project.data["images"][0]
    project.save(r, [Box(19, 0, 0, 20, 20)], "Completed")
    names[19] = "renamed"
    project.migrate_classes(names, dict(enumerate(range(20))))
    assert Project.open(project.path).data["images"][0]["boxes"][0]["class_id"] == 19


def test_cross_split_duplicate_detection(project, tmp_path):
    folder = tmp_path / "dupe"
    folder.mkdir()
    Image.new("RGB", (200, 100), "gray").save(folder / "same.png")
    project.import_folder(folder)
    project.data["images"][0]["split"] = "train"
    project.data["images"][1]["split"] = "valid"
    project.commit()
    issues = validate(project)
    assert any("trùng" in s for s in issues) and any("gần giống" in s for s in issues)


def test_export_transaction_failure(project, tmp_path, monkeypatch):
    import app.dataset.operations as ops

    project.save(project.data["images"][0], [Box(0, 1, 2, 10, 20)], "Completed")

    def fail(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(ops.shutil, "copy2", fail)
    with pytest.raises(OSError):
        export_dataset(project, tmp_path / "output")
    assert not (tmp_path / "output").exists() and not list(
        tmp_path.glob(".annotation-export-*")
    )


def test_migration_blocked_by_pending_draft(project):
    r = project.data["images"][0]
    project.draft(r, [Box(0, 0, 0, 10, 10)], "In Progress")
    before = project.path.read_bytes()
    with pytest.raises(ValueError):
        project.migrate_classes(["bus", "car"], {0: 1, 1: 0})
    assert project.path.read_bytes() == before
