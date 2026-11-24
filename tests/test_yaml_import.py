import tempfile
import unittest
from pathlib import Path
from PIL import Image
import yaml
from app.core.project import Project
from app.dataset.yaml_import import read_dataset


class YamlImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = self.root / "dataset"
        for split in ("train", "valid"):
            images = self.dataset / split / "images"
            labels = self.dataset / split / "labels"
            images.mkdir(parents=True)
            labels.mkdir()
            Image.new("RGB", (100, 80)).save(images / "one.png")
            (labels / "one.txt").write_text("0 .5 .5 .2 .2\n")
        self.config = self.root / "data.yaml"
        self.write_config()

    def write_config(self, **updates):
        config = dict(path="dataset", names={0: "car"}, nc=1,
                      train="train/images", val="valid/images")
        config.update(updates)
        self.config.write_text(yaml.safe_dump(config), encoding="utf-8")

    def test_import_labels_and_splits(self):
        project = Project.create(self.root / "project", "Test", ["car"])
        self.assertEqual(project.import_yaml(self.config), 2)
        records = Project.open(project.path).data["images"]
        self.assertEqual([r["split"] for r in records], ["train", "valid"])
        self.assertTrue(all(len(r["boxes"]) == 1 for r in records))
        self.assertTrue(all((project.root / r["path"]).exists() for r in records))
        self.assertTrue((self.dataset / "train/images/one.png").exists())

    def test_text_list_relative_to_list_file_and_dedup(self):
        (self.dataset / "train/list.txt").write_text("./images/one.png\n")
        self.write_config(train=["train/list.txt", "train/images"], names=["car"])
        names, entries = read_dataset(self.config)
        self.assertEqual(names, ["car"])
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0][1], (self.dataset / "train/labels/one.txt").resolve())

    def test_missing_label_is_unlabeled(self):
        (self.dataset / "train/labels/one.txt").unlink()
        project = Project.create(self.root / "project", "Test", ["car"])
        project.import_yaml(self.config)
        self.assertEqual(project.data["images"][0]["status"], "Unlabeled")

    def test_invalid_label_rolls_back_entire_import(self):
        (self.dataset / "valid/labels/one.txt").write_text("invalid label")
        project = Project.create(self.root / "project", "Test", ["car"])
        with self.assertRaises(ValueError):
            project.import_yaml(self.config)
        self.assertEqual(Project.open(project.path).data["images"], [])
        self.assertEqual(list((project.root / "images").rglob("*.png")), [])

    def test_reject_invalid_configuration(self):
        for updates in (
            {"names": {1: "car"}}, {"nc": 2}, {"train": "missing"},
            {"val": "train/images"},
        ):
            with self.subTest(updates=updates):
                self.write_config(**updates)
                with self.assertRaises(ValueError):
                    read_dataset(self.config)


if __name__ == "__main__":
    unittest.main()
