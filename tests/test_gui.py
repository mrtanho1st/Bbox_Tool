from copy import deepcopy
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QFileDialog
from app.gui.main_window import MainWindow
from app.gui.canvas import Canvas
from app.gui.dialogs import Busy
from app.core.model import Box


def draw(canvas, x1, y1, x2, y2):
    start = canvas.mapFromScene(QPointF(x1, y1))
    end = canvas.mapFromScene(QPointF(x2, y2))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)


def test_canvas_draw_overlap_zoom_edit(qapp, project):
    c = Canvas()
    c.resize(800, 500)
    c.show()
    qapp.processEvents()
    c.load(project.root / project.data["images"][0]["path"])
    c.names = ["car", "bus"]
    c.colors = ["#ff0000", "#00ff00"]
    c.active_class = 0
    qapp.processEvents()
    draw(c, 20, 20, 100, 80)
    draw(c, 30, 30, 90, 70)
    assert len(c.boxes) == 2
    before = deepcopy(c.boxes)
    c.zoom(1.4)
    c.resize(900, 600)
    qapp.processEvents()
    assert c.boxes == before
    c.set_mode("Select")
    p = c.mapFromScene(QPointF(50, 50))
    QTest.mouseClick(c.viewport(), Qt.MouseButton.LeftButton, pos=p)
    assert c.selection == 1
    QTest.mouseClick(
        c.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier, pos=p
    )
    assert c.selection == 0
    c.set_mode("Edit")
    draw(c, 50, 50, 60, 55)
    assert c.boxes[0].x1 > before[0].x1
    b = deepcopy(c.boxes[0])
    draw(c, b.x2, b.y2, b.x2 + 5, b.y2 + 5)
    assert c.boxes[0].x2 > b.x2
    c.close()


def test_canvas_four_clicks_create_box(qapp, project):
    c = Canvas()
    c.resize(800, 500)
    c.show()
    qapp.processEvents()
    c.load(project.root / project.data["images"][0]["path"])
    c.names = ["car", "bus"]
    c.colors = ["#ff0000", "#00ff00"]
    c.active_class = 1
    qapp.processEvents()

    for index, (x, y) in enumerate([(20, 20), (100, 20), (100, 80), (20, 80)]):
        pos = c.mapFromScene(QPointF(x, y))
        QTest.mouseClick(c.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        if index < 3:
            assert len(c.draft_points) == index + 1

    assert len(c.boxes) == 1
    box = c.boxes[0]
    assert box.class_id == 1
    assert all(
        abs(actual - expected) < 1
        for actual, expected in zip(
            (box.x1, box.y1, box.x2, box.y2), (20, 20, 100, 80)
        )
    )
    assert c.draft_points == []
    c.close()


def test_canvas_wheel_zoom_keeps_cursor_anchor(qapp, project):
    c = Canvas()
    c.resize(800, 500)
    c.show()
    qapp.processEvents()
    c.load(project.root / project.data["images"][0]["path"])
    qapp.processEvents()

    cursor = c.mapFromScene(QPointF(50, 40))
    before = c.mapToScene(cursor)
    event = QWheelEvent(
        QPointF(cursor),
        QPointF(c.viewport().mapToGlobal(cursor)),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    qapp.sendEvent(c.viewport(), event)
    after = c.mapToScene(cursor)

    assert abs(after.x() - before.x()) < 1
    assert abs(after.y() - before.y()) < 1
    c.close()


def test_main_smoke_save_reload(qapp, project, monkeypatch):
    w = MainWindow()
    w.activate(project)
    w.show()
    qapp.processEvents()
    assert w.record()["name"] == "ảnh một.png"
    w.canvas.boxes = [Box(1, 10, 20, 50, 60)]
    w.canvas.selection = 0
    w.mark_changed()
    w.refresh_boxes()
    w.status.setCurrentText("Completed")
    assert w.save()
    assert project.data["images"][0]["boxes"][0]["class_id"] == 1
    w.canvas.boxes.append(Box(0, 0, 0, 10, 10))
    w.mark_changed()
    w.save_draft()
    assert project.recover(w.record()) is not None
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard
    )
    assert w.maybe_leave()
    w.close()


def test_add_image_button_imports_files(qapp, project, monkeypatch):
    w = MainWindow()
    w.activate(project)
    source = project.root / project.data["images"][0]["path"]
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames", lambda *args, **kwargs: ([str(source)], "")
    )
    monkeypatch.setattr(w, "confirm_import", lambda: True)
    monkeypatch.setattr(Busy, "run", lambda dialog: dialog.worker.fn())
    old_count = len(project.data["images"])

    w.add_images_button.click()

    assert len(project.data["images"]) == old_count + 1
    assert w.images.count() == old_count + 1
    assert (project.root / project.data["images"][-1]["path"]).is_file()
    w.close()


def test_delete_current_image(qapp, project, monkeypatch):
    first = deepcopy(project.data["images"][0])
    project.import_files([project.root / first["path"]])
    second_id = project.data["images"][1]["id"]
    w = MainWindow()
    w.activate(project)
    try:
        w.canvas.boxes = [Box(0, 1, 1, 10, 10)]
        w.mark_changed()
        w.save_draft()
        monkeypatch.setattr(
            QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
        )
        w.delete_current_image()
        assert w.dirty
        assert len(project.data["images"]) == 2
        assert (project.root / first["path"]).exists()
        monkeypatch.setattr(
            QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
        )
        w.delete_current_image()
        assert w.record()["id"] == second_id
        assert not w.dirty
        assert not (project.root / first["path"]).exists()
        assert not project.draft_path(first).exists()
        w.delete_current_image()
        assert w.record() is None
        assert w.images.count() == w.box_list.count() == 0
        assert not w.canvas.scene().items()
        assert w.canvas.w == w.canvas.h == 0
        assert not w.history.past
        w.save_draft()
        w.delete_current_image()
    finally:
        w.dirty = False
        w.close()


def test_busy_dialog(qapp):
    from app.gui.dialogs import Busy

    assert Busy(None, "Test", lambda: 42).run() == 42
