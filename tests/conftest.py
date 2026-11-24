import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from PIL import Image
from app.core.project import Project


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "ảnh đầu vào"
    root.mkdir()
    Image.new("RGB", (200, 100), "gray").save(root / "ảnh một.png")
    p = Project.create(tmp_path / "dự án", "Test", ["car", "bus"])
    p.import_folder(root)
    return p
