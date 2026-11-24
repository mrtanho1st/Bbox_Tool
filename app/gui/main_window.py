from pathlib import Path
from copy import deepcopy
from collections import Counter
import yaml
from PySide6.QtCore import Qt, QTimer, QSettings, QSize
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPixmap, QImage
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QComboBox,
    QSplitter,
    QStackedWidget,
    QFileDialog,
    QMessageBox,
    QInputDialog,
    QDialog,
    QPlainTextEdit,
    QDialogButtonBox,
    QTableWidget,
    QTableWidgetItem,
    QProgressBar,
)
from app.core.project import Project
from app.core.model import History, STATUSES
from app.gui.canvas import Canvas
from app.gui.dialogs import ProjectDialog, ClassesDialog, Busy
from app.gui.styles import DARK
from app.dataset.operations import (
    statistics,
    report_csv,
    validate,
    audit_folder,
    split_plan,
    export_dataset,
)
from app.formats import coco
from app.services.storage import read_json, safe_child

TITLE = "Tools by hkhang17pls"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(TITLE)
        self.resize(1450, 900)
        self.settings = QSettings("hkhang17pls", TITLE)
        self.project = None
        self.index = -1
        self.dirty = False
        self.history = History()
        self.loading = False
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.make_home()
        self.make_workspace()
        self.make_menus()
        self.refresh_home()
        self.autosave = QTimer(self)
        self.autosave.timeout.connect(self.save_draft)
        self.autosave.start(
            self.settings.value("autosave_seconds", 10, type=int) * 1000
        )
        self.thumbnails = QTimer(self)
        self.thumbnails.timeout.connect(self.thumbnail_tick)
        self.thumbnails.start(150)
        self.setStyleSheet(DARK if self.settings.value("dark", True, type=bool) else "")
        self.statusBar().showMessage("Sẵn sàng · Tạo hoặc mở project để bắt đầu")

    def safe(self, fn):
        try:
            return fn()
        except Exception as e:
            QMessageBox.warning(self, "Không thể thực hiện", str(e))
            return None

    def action(self, menu, name, fn, shortcut=None, project=False):
        action = QAction(name, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(
            lambda checked=False: self.safe(
                lambda: fn() if not project or self.require_project() else None
            )
        )
        menu.addAction(action)
        return action

    def require_project(self):
        if self.project:
            return True
        QMessageBox.information(self, TITLE, "Hãy tạo hoặc mở project trước.")
        return False

    def make_home(self):
        home = QWidget()
        layout = QVBoxLayout(home)
        layout.setContentsMargins(70, 60, 70, 60)
        brand = QLabel(TITLE)
        brand.setObjectName("brand")
        layout.addWidget(brand)
        sub = QLabel("Gán nhãn ảnh • Nhiều dự án • YOLO & COCO")
        sub.setObjectName("subtitle")
        layout.addWidget(sub)
        row = QHBoxLayout()
        for text, fn in [
            ("＋ Tạo project", self.new_project),
            ("Mở project", self.open_project),
            ("Nhập YOLO dataset", self.import_yolo),
            ("Nhập từ YAML", self.import_yaml),
            ("Nhập COCO dataset", self.import_coco),
        ]:
            b = QPushButton(text)
            b.clicked.connect(lambda checked=False, fn=fn: self.safe(fn))
            row.addWidget(b)
        layout.addLayout(row)
        layout.addWidget(QLabel("DỰ ÁN GẦN ĐÂY"))
        self.recent = QListWidget()
        self.recent.itemDoubleClicked.connect(
            lambda item: self.safe(
                lambda: self.open_path(item.data(Qt.ItemDataRole.UserRole))
            )
        )
        layout.addWidget(self.recent)
        b = QPushButton("Bỏ khỏi danh sách gần đây")
        b.clicked.connect(self.remove_recent)
        layout.addWidget(b)
        layout.addWidget(
            QLabel(
                "Dataset nguồn chỉ được đọc. Mỗi project giữ bản sao ảnh và nhãn riêng."
            )
        )
        self.stack.addWidget(home)

    def refresh_home(self):
        self.recent.clear()
        for path in self.settings.value("recent", [], type=list):
            item = QListWidgetItem(Path(path).parent.name + "\n" + path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.recent.addItem(item)

    def remove_recent(self):
        item = self.recent.currentItem()
        if item:
            paths = self.settings.value("recent", [], type=list)
            path = item.data(Qt.ItemDataRole.UserRole)
            self.settings.setValue("recent", [p for p in paths if p != path])
            self.refresh_home()

    def make_workspace(self):
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        self.heading = QLabel()
        self.heading.setObjectName("subtitle")
        self.heading.setFixedHeight(34)
        layout.addWidget(self.heading)
        splitter = QSplitter()
        layout.addWidget(splitter, 1)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("IMAGE BROWSER"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm tên ảnh…")
        self.search.textChanged.connect(self.filter_images)
        ll.addWidget(self.search)
        self.filter = QComboBox()
        self.filter.addItems(["Tất cả"] + STATUSES)
        self.filter.currentTextChanged.connect(self.filter_images)
        ll.addWidget(self.filter)
        self.add_images_button = QPushButton("＋ Thêm ảnh vào project")
        self.add_images_button.clicked.connect(
            lambda: self.safe(self.import_images)
        )
        ll.addWidget(self.add_images_button)
        self.images = QListWidget()
        self.images.setIconSize(QSize(54, 42))
        self.images.currentRowChanged.connect(self.navigate_row)
        ll.addWidget(self.images)
        delete_image = QPushButton("Xóa ảnh + label · Ctrl+Delete")
        delete_image.clicked.connect(lambda: self.safe(self.delete_current_image))
        ll.addWidget(delete_image)
        self.progress = QLabel()
        ll.addWidget(self.progress)
        splitter.addWidget(left)
        self.canvas = Canvas()
        self.canvas.edited.connect(self.canvas_edited)
        self.canvas.selected.connect(self.select_box)
        self.canvas.zoomed.connect(lambda _: self.update_status())
        splitter.addWidget(self.canvas)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("CLASSES"))
        self.class_search = QLineEdit()
        self.class_search.setPlaceholderText("Tìm class…")
        self.class_search.textChanged.connect(self.filter_classes)
        rl.addWidget(self.class_search)
        self.classes = QListWidget()
        self.classes.currentRowChanged.connect(self.class_selected)
        rl.addWidget(self.classes, 2)
        assign = QPushButton("Gán class đang chọn cho box")
        assign.clicked.connect(lambda: self.safe(self.assign_class))
        rl.addWidget(assign)
        rl.addWidget(QLabel("BOUNDING BOXES · chọn được cả box bên dưới"))
        self.box_list = QListWidget()
        self.box_list.currentRowChanged.connect(self.list_select)
        rl.addWidget(self.box_list, 2)
        self.properties = QLabel("Chưa chọn box")
        self.properties.setWordWrap(True)
        rl.addWidget(self.properties)
        self.status = QComboBox()
        self.status.addItems(STATUSES)
        self.status.currentTextChanged.connect(self.status_changed)
        rl.addWidget(self.status)
        self.split = QComboBox()
        self.split.addItems(["unassigned", "train", "valid", "test"])
        self.split.currentTextChanged.connect(self.split_changed)
        rl.addWidget(QLabel("Tập dữ liệu"))
        rl.addWidget(self.split)
        save = QPushButton("Lưu annotation · Ctrl+S")
        save.clicked.connect(lambda: self.safe(self.save))
        rl.addWidget(save)
        splitter.addWidget(right)
        splitter.setSizes([260, 870, 300])
        self.stack.addWidget(workspace)

    def make_menus(self):
        file = self.menuBar().addMenu("File")
        for name, fn, key in [
            ("New Project", self.new_project, "Ctrl+N"),
            ("Open Project", self.open_project, "Ctrl+O"),
            ("Save", self.save, "Ctrl+S"),
            ("Save All", self.save, "Ctrl+Shift+S"),
            ("Close Project", self.close_project, None),
            ("Exit", self.close, "Ctrl+Q"),
        ]:
            self.action(file, name, fn, key)
        project = self.menuBar().addMenu("Project")
        self.action(file, "Settings", self.app_settings)
        self.action(project, "Project Settings", self.project_settings, project=True)
        self.action(project, "Manage Classes", self.manage_classes, project=True)
        self.action(project, "Duplicate Project", self.duplicate_project, project=True)
        self.action(project, "Recent Projects", self.close_project)
        dataset = self.menuBar().addMenu("Dataset")
        for name, fn in [
            ("Import Folder", self.import_folder),
            ("Import Images", self.import_images),
            ("Import YOLO Dataset", self.import_yolo),
            ("Import YAML Dataset", self.import_yaml),
            ("Import COCO Dataset", self.import_coco),
            ("Dataset Statistics", self.show_stats),
            ("Validate Annotations / Duplicates", self.validation),
            ("Export YOLO", lambda: self.export("yolo")),
            ("Export COCO", lambda: self.export("coco")),
            ("Split & Export YOLO", self.split_export),
        ]:
            self.action(dataset, name, fn)
        annotation = self.menuBar().addMenu("Annotation")
        self.action(dataset, "Xóa ảnh + label đang hiển thị",
                    self.delete_current_image, "Ctrl+Delete", True)
        toolbar = self.addToolBar("Annotation")
        toolbar.setMovable(False)
        modes = QActionGroup(self)
        modes.setExclusive(True)
        for name, key in [("Draw", "B"), ("Select", "V"), ("Edit", "E"), ("Pan", "G")]:
            a = QAction(name, self)
            a.setCheckable(True)
            a.setShortcut(key)
            a.setChecked(name == "Draw")
            modes.addAction(a)
            a.triggered.connect(
                lambda checked, n=name: (
                    self.canvas.set_mode(n),
                    self.canvas.render_boxes(),
                )
            )
            annotation.addAction(a)
            toolbar.addAction(a)
        toolbar.addSeparator()
        for name, fn, key in [
            ("Undo", self.undo, "Ctrl+Z"),
            ("Redo", self.redo, "Ctrl+Y"),
            ("Delete Box", self.delete_box, "Delete"),
            ("Duplicate Box", self.duplicate_box, "Ctrl+D"),
            ("Clear Boxes", self.clear_boxes, None),
        ]:
            a = self.action(annotation, name, fn, key, True)
            toolbar.addAction(a)
        toolbar.addSeparator()
        for name, fn, key in [
            ("Previous", lambda: self.navigate(self.index - 1), "P"),
            ("Next", lambda: self.navigate(self.index + 1), "N"),
            ("Save", self.save, None),
        ]:
            toolbar.addAction(self.action(annotation, name, fn, key, True))
        view = self.menuBar().addMenu("View")
        for name, fn, key in [
            ("Zoom In", lambda: self.canvas.zoom(1.2), "+"),
            ("Zoom Out", lambda: self.canvas.zoom(1 / 1.2), "-"),
            ("Fit Image", self.canvas.fit, "F"),
        ]:
            self.action(view, name, fn, key)
        for name, field in [
            ("Show Annotations", "show_boxes"),
            ("Show Labels", "show_labels"),
            ("Show Grid", "grid"),
        ]:
            a = QAction(name, self)
            a.setCheckable(True)
            a.setChecked(getattr(self.canvas, field))
            a.triggered.connect(lambda checked, f=field: self.toggle_view(f, checked))
            view.addAction(a)
        self.action(view, "Dark / Light Theme", self.toggle_theme)
        helpmenu = self.menuBar().addMenu("Help")
        self.action(helpmenu, "User Guide / Keyboard Shortcuts", self.help)
        self.action(
            helpmenu,
            "About " + TITLE,
            lambda: QMessageBox.information(
                self,
                TITLE,
                TITLE
                + "\nDesktop Bounding Box Annotation · v1.0\nYOLO & COCO Object Detection\nKhông hỗ trợ segmentation/keypoints.",
            ),
        )
        for i in range(9):
            a = QAction(self)
            a.setShortcut(str(i + 1))
            a.triggered.connect(lambda checked=False, i=i: self.quick_class(i))
            self.addAction(a)

    def app_settings(self):
        seconds, ok = QInputDialog.getInt(
            self,
            "Settings",
            "Lưu bản nháp mỗi bao nhiêu giây?",
            self.settings.value("autosave_seconds", 10, type=int),
            2,
            300,
        )
        if ok:
            self.settings.setValue("autosave_seconds", seconds)
            self.autosave.start(seconds * 1000)

    def toggle_view(self, field, value):
        setattr(self.canvas, field, value)
        self.canvas.render_boxes()
        self.canvas.viewport().update()

    def toggle_theme(self):
        dark = not bool(self.styleSheet())
        self.setStyleSheet(DARK if dark else "")
        self.settings.setValue("dark", dark)

    def record(self):
        return (
            self.project.data["images"][self.index]
            if self.project and 0 <= self.index < len(self.project.data["images"])
            else None
        )

    def new_project(self, names=None):
        if not self.maybe_leave():
            return None
        d = ProjectDialog(self, names)
        if d.exec() != QDialog.DialogCode.Accepted:
            return None
        name, names, description = d.values()
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục project RỖNG")
        if not folder:
            return None
        p = Project.create(folder, name, names, description)
        self.activate(p)
        return p

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Mở project", "", "Project (project.json *.json)"
        )
        if path:
            self.open_path(path)

    def open_path(self, path):
        if not self.maybe_leave():
            return
        self.activate(Project.open(path))

    def activate(self, project):
        self.project = project
        self.index = -1
        self.dirty = False
        self.canvas.scene().clear()
        self.canvas.items_drawn = []
        self.canvas.w = 0
        self.canvas.boxes = []
        paths = self.settings.value("recent", [], type=list)
        p = str(project.path)
        self.settings.setValue("recent", [p] + [x for x in paths if x != p][:14])
        self.refresh_home()
        self.heading.setText(TITLE + "  /  " + project.data["name"])
        self.setWindowTitle(project.data["name"] + " — " + TITLE)
        self.stack.setCurrentIndex(1)
        self.refresh_classes()
        self.refresh_images()
        if project.data["images"]:
            self.navigate(0)
        self.update_status()

    def refresh_classes(self):
        self.classes.blockSignals(True)
        self.classes.clear()
        for i, name in enumerate(self.project.data["classes"]):
            item = QListWidgetItem(f"{i} · {name}")
            item.setForeground(QColor(self.project.data["colors"][i]))
            self.classes.addItem(item)
        self.canvas.names = self.project.data["classes"]
        self.canvas.colors = self.project.data["colors"]
        self.classes.blockSignals(False)
        self.classes.setCurrentRow(0)

    def refresh_images(self):
        self.images.blockSignals(True)
        self.images.clear()
        for r in self.project.data["images"]:
            item = QListWidgetItem(
                f"{r['name']}\n{r['status']} · {len(r['boxes'])} boxes"
            )
            self.images.addItem(item)
        self.images.setCurrentRow(self.index)
        self.images.blockSignals(False)
        self.filter_images()
        self.update_status()

    def filter_images(self, *args):
        if not self.project:
            return
        text = self.search.text().casefold()
        status = self.filter.currentText()
        for i, r in enumerate(self.project.data["images"]):
            self.images.item(i).setHidden(
                text not in r["name"].casefold()
                or (status != "Tất cả" and r["status"] != status)
            )

    def filter_classes(self, text):
        for i in range(self.classes.count()):
            self.classes.item(i).setHidden(
                text.casefold() not in self.classes.item(i).text().casefold()
            )

    def thumbnail_tick(self):
        if not self.project or self.stack.currentIndex() != 1:
            return
        # Only visible rows; icons outside viewport are cleared to bound RAM.
        made = 0
        for i in range(self.images.count()):
            item = self.images.item(i)
            visible = not item.isHidden() and self.images.visualItemRect(
                item
            ).intersects(self.images.viewport().rect())
            if not visible:
                if not item.icon().isNull():
                    item.setIcon(QIcon())
            elif item.icon().isNull() and made < 2:
                try:
                    from PIL import Image

                    with Image.open(
                        safe_child(
                            self.project.root, self.project.data["images"][i]["path"]
                        )
                    ) as im:
                        im.thumbnail((54, 42))
                        rgb = im.convert("RGB")
                        q = QImage(
                            rgb.tobytes(),
                            rgb.width,
                            rgb.height,
                            rgb.width * 3,
                            QImage.Format.Format_RGB888,
                        ).copy()
                    item.setIcon(QIcon(QPixmap.fromImage(q)))
                    made += 1
                except Exception:
                    pass

    def navigate_row(self, row):
        if not self.loading:
            self.safe(lambda: self.navigate(row))

    def navigate(self, index):
        if not self.project or not 0 <= index < len(self.project.data["images"]):
            return
        if index == self.index:
            return
        if not self.maybe_leave():
            self.images.blockSignals(True)
            self.images.setCurrentRow(self.index)
            self.images.blockSignals(False)
            return
        old = self.index
        try:
            r = self.project.data["images"][index]
            self.canvas.load(safe_child(self.project.root, r["path"]))
        except Exception:
            self.images.blockSignals(True)
            self.images.setCurrentRow(old)
            self.images.blockSignals(False)
            raise
        self.index = index
        self.history = History()
        self.loading = True
        self.canvas.boxes = self.project.boxes(r)
        self.status.setCurrentText(r["status"])
        self.split.setCurrentText(r["split"])
        self.loading = False
        self.dirty = False
        recovered = self.project.recover(r)
        if recovered:
            decision = QMessageBox.question(
                self,
                "Khôi phục bản nháp",
                "Có bản nháp chưa lưu của ảnh này. Khôi phục?\nChọn No sẽ giữ bản lưu và xóa bản nháp.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if decision == QMessageBox.StandardButton.Yes:
                self.canvas.boxes, status = recovered
                self.loading = True
                self.status.setCurrentText(status)
                self.loading = False
                self.dirty = True
            else:
                self.project.discard_draft(r)
        self.images.blockSignals(True)
        self.images.setCurrentRow(index)
        self.images.blockSignals(False)
        self.refresh_boxes()
        self.canvas.render_boxes()
        self.update_status()

    def canvas_edited(self, before):
        self.history.push(before)
        self.mark_changed()
        self.refresh_boxes()

    def mark_changed(self):
        self.dirty = True
        self.loading = True
        self.status.setCurrentText("In Progress")
        self.loading = False
        self.update_status()

    def refresh_boxes(self):
        self.box_list.blockSignals(True)
        self.box_list.clear()
        for i, b in enumerate(self.canvas.boxes):
            self.box_list.addItem(
                f"{i + 1} · "
                + ("Chưa gán" if b.class_id is None else self.canvas.names[b.class_id])
            )
        self.box_list.setCurrentRow(self.canvas.selection)
        self.box_list.blockSignals(False)
        counts = Counter(b.class_id for b in self.canvas.boxes)
        if self.project:
            for i, n in enumerate(self.project.data["classes"]):
                self.classes.item(i).setText(f"{i} · {n}   ({counts[i]})")
        self.select_box(self.canvas.selection)
        self.update_status()

    def select_box(self, index):
        self.box_list.blockSignals(True)
        self.box_list.setCurrentRow(index)
        self.box_list.blockSignals(False)
        if 0 <= index < len(self.canvas.boxes):
            b = self.canvas.boxes[index]
            self.properties.setText(
                f"x1={b.x1:.2f}  y1={b.y1:.2f}\nx2={b.x2:.2f}  y2={b.y2:.2f}\nW={b.x2 - b.x1:.2f} × H={b.y2 - b.y1:.2f} px"
            )
        else:
            self.properties.setText("Chưa chọn box")

    def list_select(self, index):
        self.canvas.selection = index
        self.canvas.render_boxes()
        self.select_box(index)

    def class_selected(self, index):
        self.canvas.active_class = index if index >= 0 else None

    def quick_class(self, index):
        if self.project and index < len(self.project.data["classes"]):
            self.classes.setCurrentRow(index)
            self.safe(self.assign_class)

    def assign_class(self):
        i = self.canvas.selection
        cls = self.classes.currentRow()
        if i < 0 or cls < 0:
            return
        self.history.push(self.canvas.boxes)
        self.canvas.boxes[i].class_id = cls
        self.mark_changed()
        self.refresh_boxes()
        self.canvas.render_boxes()

    def delete_current_image(self):
        record = self.record()
        if record is None:
            return
        if QMessageBox.question(
            self,
            "Xóa ảnh + label",
            f"Xóa ảnh {record['name']} cùng toàn bộ label và bản nháp khỏi project?\n"
            "Thay đổi chưa lưu của ảnh này cũng sẽ bị xóa. Không thể Undo.\n"
            "Dataset nguồn không bị thay đổi.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        old_index = self.index
        self.project.delete_image(record)
        self.dirty = False
        self.index = -1
        self.history = History()
        self.canvas.scene().clear()
        self.canvas.items_drawn = []
        self.canvas.boxes = []
        self.canvas.selection = -1
        self.canvas.w = self.canvas.h = 0
        self.canvas.start = self.canvas.original = self.canvas.preview = None
        self.canvas.setSceneRect(0, 0, 0, 0)
        self.loading = True
        self.status.setCurrentIndex(0)
        self.split.setCurrentIndex(0)
        self.loading = False
        self.refresh_boxes()
        self.refresh_images()
        if self.project.data["images"]:
            self.navigate(min(old_index, len(self.project.data["images"]) - 1))
        else:
            self.statusBar().showMessage("Project chưa có ảnh. Hãy nhập thêm ảnh.")

    def delete_box(self):
        if self.canvas.selection < 0:
            return
        self.history.push(self.canvas.boxes)
        self.canvas.boxes.pop(self.canvas.selection)
        self.canvas.selection = -1
        self.mark_changed()
        self.refresh_boxes()
        self.canvas.render_boxes()

    def duplicate_box(self):
        if self.canvas.selection < 0:
            return
        self.history.push(self.canvas.boxes)
        b = self.canvas.boxes[self.canvas.selection]
        self.canvas.boxes.append(b.moved(10, 10, self.canvas.w, self.canvas.h))
        self.canvas.selection = len(self.canvas.boxes) - 1
        self.mark_changed()
        self.refresh_boxes()
        self.canvas.render_boxes()

    def clear_boxes(self):
        if (
            self.canvas.boxes
            and QMessageBox.question(
                self, "Xóa box", "Xóa tất cả box của ảnh? Có thể Undo."
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.history.push(self.canvas.boxes)
            self.canvas.boxes = []
            self.canvas.selection = -1
            self.mark_changed()
            self.refresh_boxes()
            self.canvas.render_boxes()

    def undo(self):
        if not self.history.past:
            return
        self.canvas.boxes = self.history.undo(self.canvas.boxes)
        self.canvas.selection = -1
        self.mark_changed()
        self.refresh_boxes()
        self.canvas.render_boxes()

    def redo(self):
        if not self.history.future:
            return
        self.canvas.boxes = self.history.redo(self.canvas.boxes)
        self.canvas.selection = -1
        self.mark_changed()
        self.refresh_boxes()
        self.canvas.render_boxes()

    def status_changed(self, text):
        if not self.loading and self.record():
            self.dirty = True
            self.update_status()

    def split_changed(self, text):
        if self.loading or not self.record():
            return
        r = self.record()
        old = r["split"]
        if text == old:
            return
        if (
            QMessageBox.question(
                self,
                "Thay đổi tập",
                f"{r['name']}: {old} → {text}?\nChỉ đổi metadata, không di chuyển ảnh nguồn.",
            )
            == QMessageBox.StandardButton.Yes
        ):

            def apply():
                before = deepcopy(self.project.data)
                r["split"] = text
                try:
                    self.project.commit()
                except Exception:
                    self.project.data = before
                    raise

            self.safe(apply)
        self.loading = True
        self.split.setCurrentText(self.record()["split"])
        self.loading = False

    def save(self):
        if not self.dirty or not self.record():
            return True
        status = self.status.currentText()
        if not self.canvas.boxes and status == "Confirmed Empty":
            if (
                QMessageBox.question(
                    self,
                    "Xác nhận ảnh rỗng",
                    "Xác nhận ảnh này KHÔNG có đối tượng cần gán nhãn?",
                )
                != QMessageBox.StandardButton.Yes
            ):
                return False
        self.project.save(self.record(), self.canvas.boxes, status)
        self.dirty = False
        self.refresh_images()
        self.update_status()
        return True

    def save_draft(self):
        if self.dirty and self.record():
            try:
                self.project.draft(
                    self.record(), self.canvas.boxes, self.status.currentText()
                )
            except Exception as e:
                self.statusBar().showMessage("Lỗi lưu bản nháp: " + str(e))

    def maybe_leave(self):
        if not self.dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Chưa lưu",
            "Lưu thay đổi trước khi chuyển?\nDiscard bỏ thay đổi và bản nháp của ảnh này.",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            try:
                return self.save()
            except Exception as e:
                QMessageBox.warning(self, "Chưa lưu", str(e))
                return False
        self.project.discard_draft(self.record())
        self.dirty = False
        self.canvas.boxes = self.project.boxes(self.record())
        self.canvas.selection = -1
        self.history = History()
        self.loading = True
        self.status.setCurrentText(self.record()["status"])
        self.loading = False
        self.refresh_boxes()
        self.canvas.render_boxes()
        return True

    def close_project(self):
        if not self.maybe_leave():
            return
        self.project = None
        self.index = -1
        self.dirty = False
        self.stack.setCurrentIndex(0)
        self.setWindowTitle(TITLE)
        self.refresh_home()

    def closeEvent(self, event):
        if self.maybe_leave():
            event.accept()
        else:
            event.ignore()

    def update_status(self):
        r = self.record()
        if self.project:
            completed = sum(
                x["status"] in ("Completed", "Reviewed", "Confirmed Empty")
                for x in self.project.data["images"]
            )
            total = len(self.project.data["images"])
            self.progress.setText(f"Hoàn thành {completed}/{total}")
        if r:
            self.statusBar().showMessage(
                f"{r['name']}  |  {r['width']}×{r['height']}  |  {self.index + 1}/{len(self.project.data['images'])}  |  {len(self.canvas.boxes)} boxes  |  Zoom {self.canvas.transform().m11():.0%}  |  "
                + ("CHƯA LƯU" if self.dirty else "Đã lưu")
            )

    def import_folder(self):
        if not self.require_project() or not self.maybe_leave():
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục ảnh (quét cả thư mục con)"
        )
        if not folder:
            return
        labels = None
        if (
            QMessageBox.question(
                self, "Nhãn có sẵn", "Có thư mục nhãn YOLO tương ứng cần nhập không?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            labels = QFileDialog.getExistingDirectory(
                self, "Chọn gốc nhãn, cấu trúc con giống gốc ảnh"
            )
            if not labels:
                return
            issues = audit_folder(Path(folder), Path(labels))
            if issues and not self.confirm_report("Kiểm tra đầu vào", issues):
                return
        if not self.confirm_import():
            return
        Busy(
            self, "Đang nhập ảnh", lambda: self.project.import_folder(folder, labels)
        ).run()
        self.after_import()

    def import_images(self):
        if not self.require_project() or not self.maybe_leave():
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn ảnh",
            "",
            "Images (*.jpg *.jpeg *.png *.bmp *.webp *.heic *.heif)",
        )
        if paths and self.confirm_import():
            Busy(self, "Đang nhập ảnh", lambda: self.project.import_files(paths)).run()
            self.after_import()

    def confirm_import(self):
        return (
            QMessageBox.question(
                self,
                "Nhập dataset",
                "Sao chép ảnh vào project. Ảnh có EXIF xoay sẽ tạo bản PNG đúng chiều.\nNhãn đầu vào được hiểu theo tọa độ pixel thô trước EXIF.\nTiếp tục?",
            )
            == QMessageBox.StandardButton.Yes
        )

    def import_yolo(self):
        root = QFileDialog.getExistingDirectory(
            self, "Chọn dataset có images/, labels/, data.yaml"
        )
        if not root:
            return
        root = Path(root)
        config = yaml.safe_load((root / "data.yaml").read_text(encoding="utf-8-sig"))
        names = config["names"]
        if isinstance(names, dict):
            converted = {int(k): v for k, v in names.items()}
            if sorted(converted) != list(range(len(converted))):
                raise ValueError("YOLO names IDs phải liên tục từ 0")
            names = [converted[i] for i in range(len(converted))]
        if not (root / "images").is_dir() or not (root / "labels").is_dir():
            raise ValueError(
                "Cần cấu trúc images/ và labels/. Với cấu trúc khác, dùng Import Folder."
            )
        issues = audit_folder(root / "images", root / "labels")
        if issues and not self.confirm_report("Kiểm tra dataset nguồn", issues):
            return
        if self.project:
            if self.project.data["classes"] != names:
                raise ValueError(
                    "Classes khác project. Đóng project rồi nhập để tạo project mới."
                )
            if not self.maybe_leave():
                return
        elif not self.new_project(names):
            return
        if not self.confirm_import():
            return
        Busy(
            self,
            "Nhập YOLO",
            lambda: self.project.import_folder(root / "images", root / "labels"),
        ).run()
        self.after_import()

    def import_yaml(self):
        from app.dataset.yaml_import import read_dataset

        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn cấu hình dataset YOLO", "", "YAML (*.yaml *.yml)"
        )
        if not path:
            return
        names, entries = read_dataset(path)
        if self.project:
            if self.project.data["classes"] != names:
                raise ValueError(
                    "Classes khác project. Đóng project rồi nhập để tạo project mới."
                )
            if not self.maybe_leave():
                return
        elif not self.new_project(names):
            return
        missing = [str(image) for image, label, split in entries if not label.is_file()]
        if missing and not self.confirm_report(
            "Ảnh thiếu label sẽ được nhập với trạng thái Unlabeled", missing
        ):
            return
        if not self.confirm_import():
            return
        Busy(self, "Nhập dataset từ YAML", lambda: self.project.import_yaml(path)).run()
        self.after_import()

    def import_coco(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn COCO annotations JSON", "", "JSON (*.json)"
        )
        if not path:
            return
        names, _ = coco.loads(read_json(path))
        root = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục gốc tương ứng file_name trong COCO"
        )
        if not root:
            return
        if self.project:
            if self.project.data["classes"] != names:
                raise ValueError(
                    "Class COCO khác project. Đóng project rồi nhập để tạo project mới."
                )
            if not self.maybe_leave():
                return
        elif not self.new_project(names):
            return
        if not self.confirm_import():
            return
        Busy(self, "Nhập COCO", lambda: self.project.import_coco(path, root)).run()
        self.after_import()

    def after_import(self):
        self.refresh_images()
        if self.index < 0 and self.project.data["images"]:
            self.navigate(0)

    def project_settings(self):
        name, ok = QInputDialog.getText(
            self, "Project Settings", "Tên project:", text=self.project.data["name"]
        )
        if not ok or not name.strip():
            return
        description, ok = QInputDialog.getMultiLineText(
            self, "Project Settings", "Mô tả:", self.project.data["description"]
        )
        if ok:
            before = deepcopy(self.project.data)
            self.project.data["name"] = name
            self.project.data["description"] = description
            try:
                self.project.commit()
            except Exception:
                self.project.data = before
                raise
            self.heading.setText(TITLE + " / " + name)
            self.setWindowTitle(name + " — " + TITLE)

    def manage_classes(self):
        if not self.maybe_leave():
            return
        d = ClassesDialog(
            self, self.project.data["classes"], self.project.data["colors"]
        )
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        names, mapping, colors = d.values()
        lines = [
            f"{i}: {name} → "
            + (f"{mapping[i]}: {names[mapping[i]]}" if i in mapping else "XÓA")
            for i, name in enumerate(self.project.data["classes"])
        ]
        if not self.confirm_report("Ánh xạ class · có backup project.json", lines):
            return
        self.project.migrate_classes(names, mapping, colors)
        self.refresh_classes()
        if self.record():
            self.canvas.boxes = self.project.boxes(self.record())
            self.history = History()
            self.refresh_boxes()
            self.canvas.render_boxes()

    def duplicate_project(self):
        if not self.maybe_leave():
            return
        parent = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa bản sao")
        if not parent:
            return
        name, ok = QInputDialog.getText(self, "Bản sao", "Tên thư mục mới:")
        if ok and name:
            destination = self.output_child(parent, name)
            p = Busy(
                self, "Sao chép project", lambda: self.project.duplicate(destination)
            ).run()
            self.activate(p)

    def confirm_report(self, title, lines):
        d = QDialog(self)
        d.setWindowTitle(title)
        d.resize(760, 500)
        l = QVBoxLayout(d)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText("\n".join(lines))
        l.addWidget(text)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(d.accept)
        buttons.rejected.connect(d.reject)
        l.addWidget(buttons)
        return d.exec() == QDialog.DialogCode.Accepted

    def show_stats(self):
        if not self.require_project():
            return
        stats = statistics(self.project)
        d = QDialog(self)
        d.setWindowTitle("Dataset Statistics · dữ liệu đã lưu")
        d.resize(720, 650)
        l = QVBoxLayout(d)
        summary = QLabel(
            "\n".join(f"{k}: {v}" for k, v in stats.items() if k != "classes")
        )
        summary.setWordWrap(True)
        l.addWidget(summary)
        table = QTableWidget(len(stats["classes"]), 4)
        table.setHorizontalHeaderLabels(["Class", "Objects", "Images", "Phân bố"])
        maximum = max([c["objects"] for c in stats["classes"]] + [1])
        for i, c in enumerate(stats["classes"]):
            for col, value in enumerate([c["name"], c["objects"], c["images"]]):
                table.setItem(i, col, QTableWidgetItem(str(value)))
            bar = QProgressBar()
            bar.setRange(0, maximum)
            bar.setValue(c["objects"])
            bar.setFormat(str(c["objects"]))
            table.setCellWidget(i, 3, bar)
        l.addWidget(table)
        b = QPushButton("Xuất CSV")
        b.clicked.connect(lambda: self.safe(self.export_stats))
        l.addWidget(b)
        d.exec()

    def export_stats(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Xuất báo cáo CSV mới", "", "CSV (*.csv)"
        )
        if path:
            report_csv(self.project, path)

    def validation(self):
        if not self.require_project():
            return
        issues = Busy(
            self, "Kiểm tra nhãn và ảnh trùng/gần giống", lambda: validate(self.project)
        ).run()
        self.confirm_report(
            "Kết quả kiểm tra (dữ liệu đã lưu)",
            issues
            or ["Không phát hiện lỗi. Gần giống dùng dHash, cần kiểm tra thủ công."],
        )

    def output_child(self, parent, name):
        if not name.strip() or Path(name).name != name or name in (".", ".."):
            raise ValueError("Nhập một tên thư mục đơn, không chứa đường dẫn.")
        return safe_child(parent, name)

    def export(self, fmt="yolo", plan=None):
        if not self.require_project() or not self.maybe_leave():
            return
        parent = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục chứa dataset xuất"
        )
        if not parent:
            return
        name, ok = QInputDialog.getText(
            self,
            "Xuất dataset",
            "Tên thư mục MỚI:",
            text=self.project.data["name"] + "-" + fmt,
        )
        if not ok:
            return
        dest = self.output_child(parent, name)
        distribution = (
            Counter(plan.values())
            if plan
            else Counter(r["split"] for r in self.project.data["images"])
        )
        if not self.confirm_report(
            "Xem trước xuất",
            [
                f"Đích: {dest}",
                f"Định dạng: {fmt}",
                f"Ảnh: {len(self.project.data['images'])}",
                f"Phân bố: {dict(distribution)}",
                "Sao chép ảnh; giữ nguyên project và dataset gốc.",
                "unassigned chưa dùng làm train/valid; hãy chia tập trước khi train.",
            ],
        ):
            return
        Busy(
            self, "Xuất dataset", lambda: export_dataset(self.project, dest, fmt, plan)
        ).run()
        QMessageBox.information(self, "Đã xuất", str(dest))

    def split_export(self):
        if not self.require_project() or not self.maybe_leave():
            return
        ratios, ok = QInputDialog.getText(
            self, "Tỷ lệ chia tập", "train,valid,test (tổng 1):", text="0.8,0.1,0.1"
        )
        if not ok:
            return
        seed, ok = QInputDialog.getInt(self, "Seed", "Seed cố định:", 42, 0, 2147483647)
        if not ok:
            return
        plan = split_plan(self.project, [float(v) for v in ratios.split(",")], seed)
        # Audit on proposed assignments so leakage warning reflects the actual planned split.
        clone = Project(self.project.path, deepcopy(self.project.data))
        for r in clone.data["images"]:
            r["split"] = plan[r["id"]]
        issues = Busy(
            self, "Kiểm tra rò rỉ dữ liệu theo phương án chia", lambda: validate(clone)
        ).run()
        if issues and not self.confirm_report(
            "Cảnh báo trước khi chia · xem lại ảnh trùng", issues
        ):
            return
        self.export("yolo", plan)

    def help(self):
        self.confirm_report(
            "Hướng dẫn nhanh",
            [
                "1. New Project → tên và classes → thư mục project rỗng.",
                "2. Import Folder/Images hoặc Import YOLO/COCO. Dataset nguồn không thay đổi.",
                "3. B: Draw, V: Select, E: Edit (kéo góc để resize), G: Pan.",
                "4. Chọn class trước khi vẽ. Phím 1–9 chọn/gán 9 class đầu.",
                "5. Alt+click luân phiên box chồng nhau; hoặc chọn từ danh sách bên phải.",
                "6. Cuộn chuột: zoom; F: fit; Ctrl+Z/Y: undo/redo; Delete: xóa; Ctrl+D: nhân đôi.",
                "7. N/P: ảnh tiếp/trước; Ctrl+S: lưu. Có hỏi khi chuyển ảnh chưa lưu.",
                "8. Ảnh không có đối tượng: chọn Confirmed Empty rồi lưu; không tự tạo nhãn rỗng.",
                "9. Autosave bản nháp mỗi 10 giây; mở lại ảnh để khôi phục.",
                "10. Save lưu trong project.json; Export YOLO xuất các file .txt + data.yaml.",
                "11. Dataset Statistics / Validate / Export / Split & Export nằm trong menu Dataset.",
                "12. Backup trong .backups. Đóng ứng dụng trước khi phục hồi project.json từ backup.",
            ],
        )
