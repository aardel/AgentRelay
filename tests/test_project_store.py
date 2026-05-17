"""Tests for project workspace registry."""

import tempfile
import unittest
from pathlib import Path

from project_store import ProjectStore, path_under_project


class ProjectStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProjectStore(Path(self.tmp.name) / "projects.json")
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_register_and_set_active(self) -> None:
        project = self.store.register(self.root, name="Demo")
        self.assertEqual(project["name"], "Demo")
        active = self.store.set_active(project["id"])
        self.assertIsNotNone(active)
        self.assertEqual(self.store.get_active()["id"], project["id"])

    def test_path_under_project(self) -> None:
        child = self.root / "src" / "main.py"
        child.parent.mkdir(parents=True)
        child.write_text("x", encoding="utf-8")
        self.assertTrue(path_under_project(child, self.root))
        self.assertFalse(path_under_project(Path(self.tmp.name), self.root))

    def test_clear_active(self) -> None:
        project = self.store.set_active_path(self.root)
        self.assertIsNotNone(project)
        self.store.set_active(None)
        self.assertIsNone(self.store.get_active())


if __name__ == "__main__":
    unittest.main()
