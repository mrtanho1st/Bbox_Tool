from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QDialogButtonBox,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHBoxLayout,
    QColorDialog,
    QFileDialog,
    QMessageBox,
    QLabel,
    QProgressBar,
    QHeaderView,
)
from app.core.model import class_names, color


class Worker(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.result.emit(self.fn())
        except Exception as e:
            self.failed.emit(str(e))


class Busy(QDialog):
    def __init__(self, parent, title, fn):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title + "…"))
        bar = QProgressBar()
        bar.setRange(0, 0)
        layout.addWidget(bar)
        self.value = None
        self.error = None
        self.worker = Worker(fn)
        self.worker.result.connect(self.success)
        self.worker.failed.connect(self.failure)

    def success(self, value):
        self.value = value
        self.accept()

    def failure(self, error):
        self.error = error
        self.accept()

    def reject(self):
        pass

    def run(self):
        self.worker.start()
        self.exec()
        self.worker.wait()
        if self.error:
            raise ValueError(self.error)
        return self.value


class ProjectDialog(QDialog):
    def __init__(self, parent, names=None):
        super().__init__(parent)
        self.setWindowTitle("Tạo project · Tools by hkhang17pls")
        self.resize(460, 410)
        layout = QFormLayout(self)
        self.name = QLineEdit()
        self.description = QLineEdit()
        self.names = QPlainTextEdit()
        self.names.setPlaceholderText(
            "Mỗi dòng một class, theo đúng thứ tự ID.\nVí dụ: car\nmotorcycle"
        )
        if names:
            self.names.setPlainText("\n".join(names))
        layout.addRow("Tên project", self.name)
        layout.addRow("Mô tả", self.description)
        layout.addRow("Danh sách class", self.names)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return (
            self.name.text(),
            class_names(self.names.toPlainText().splitlines()),
            self.description.text(),
        )


class ClassesDialog(QDialog):
    def __init__(self, parent, names, colors):
        super().__init__(parent)
        self.setWindowTitle("Quản lý class")
        self.resize(620, 500)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "ID mới theo thứ tự dòng. Đổi thứ tự/xóa sẽ hiện ánh xạ trước khi lưu."
            )
        )
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID cũ", "Tên class", "Màu"])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)
        for i, n in enumerate(names):
            self.add(n, i, colors[i])
        row = QHBoxLayout()
        for name, fn in [
            ("Thêm", lambda: self.add()),
            ("Xóa", self.remove),
            ("↑", lambda: self.move(-1)),
            ("↓", lambda: self.move(1)),
            ("Màu", self.choose_color),
            ("Nhập TXT", self.import_names),
            ("Xuất TXT", self.export_names),
        ]:
            b = QPushButton(name)
            b.clicked.connect(fn)
            row.addWidget(b)
        layout.addLayout(row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add(self, name="", old=None, shade=None):
        i = self.table.rowCount()
        self.table.insertRow(i)
        ident = QTableWidgetItem("new" if old is None else str(old))
        ident.setData(Qt.ItemDataRole.UserRole, old)
        ident.setFlags(ident.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(i, 0, ident)
        self.table.setItem(i, 1, QTableWidgetItem(name))
        self.table.setItem(i, 2, QTableWidgetItem(shade or color(i)))

    def remove(self):
        if self.table.currentRow() >= 0:
            self.table.removeRow(self.table.currentRow())

    def move(self, delta):
        i = self.table.currentRow()
        j = i + delta
        if not 0 <= j < self.table.rowCount() or i < 0:
            return
        for c in range(3):
            a = self.table.takeItem(i, c)
            b = self.table.takeItem(j, c)
            self.table.setItem(i, c, b)
            self.table.setItem(j, c, a)
        self.table.setCurrentCell(j, 1)

    def choose_color(self):
        i = self.table.currentRow()
        if i < 0:
            return
        shade = QColorDialog.getColor(QColor(self.table.item(i, 2).text()), self)
        if shade.isValid():
            self.table.item(i, 2).setText(shade.name())

    def import_names(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Nhập class TXT", "", "Text (*.txt)"
        )
        if path:
            try:
                from pathlib import Path

                for name in class_names(
                    Path(path).read_text(encoding="utf-8-sig").splitlines()
                ):
                    self.add(name)
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", str(e))

    def export_names(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Xuất class TXT", "", "Text (*.txt)"
        )
        if path:
            try:
                with open(path, "x", encoding="utf-8") as f:
                    f.write("\n".join(self.values()[0]))
            except Exception as e:
                QMessageBox.warning(self, "Lỗi", str(e))

    def values(self):
        names = class_names(
            [self.table.item(i, 1).text() for i in range(self.table.rowCount())]
        )
        mapping = {}
        shades = []
        for i in range(self.table.rowCount()):
            old = self.table.item(i, 0).data(Qt.ItemDataRole.UserRole)
            if old is not None:
                mapping[old] = i
            shade = self.table.item(i, 2).text()
            if not QColor(shade).isValid():
                raise ValueError("Màu không hợp lệ")
            shades.append(shade)
        return names, mapping, shades
