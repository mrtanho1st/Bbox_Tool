"""Atomic, backed-up writes. Never truncate an existing file on failure."""

import json, os, shutil, tempfile, uuid
from pathlib import Path
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_text(path, text, backup=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and path.exists():
        folder = path.parent / ".backups"
        folder.mkdir(exist_ok=True)
        shutil.copy2(path, folder / (path.name + "." + uuid.uuid4().hex + ".bak"))
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path, value, backup=True):
    atomic_text(
        path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), backup
    )


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def safe_child(root, name):
    root = Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Đường dẫn vượt thư mục: {name}")
    return path
