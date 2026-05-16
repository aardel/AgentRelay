"""GUI asset path resolution."""

import unittest
from pathlib import Path

from gui_paths import gui_directory


class GuiPathsTests(unittest.TestCase):
    def test_gui_directory_contains_index(self) -> None:
        gui = gui_directory()
        self.assertTrue((gui / "index.html").is_file(), gui)
        self.assertTrue((gui / "app.js").is_file(), gui)
        self.assertTrue((gui / "terminals.js").is_file(), gui)


if __name__ == "__main__":
    unittest.main()
