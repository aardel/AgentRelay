import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class WindowsLauncherTests(unittest.TestCase):
    def test_launcher_does_not_open_browser_from_batch(self):
        source = (ROOT / "scripts" / "Launch-AgentRelay.cmd").read_text(encoding="utf-8")

        self.assertNotIn("print_ui_url.py", source)
        self.assertNotIn("start \"\" \"%%u\"", source)

    def test_gui_launch_uses_pythonw_without_extra_console(self):
        source = (ROOT / "scripts" / "Launch-AgentRelay.cmd").read_text(encoding="utf-8")

        self.assertIn(r'\.venv\Scripts\pythonw.exe" "%ROOT%\agentrelay_gui.py"', source)
        self.assertNotIn(r'\.venv\Scripts\python.exe" "%ROOT%\agentrelay_gui.py"', source)

    def test_print_ui_url_helper_exists_for_manual_use(self):
        helper = (ROOT / "scripts" / "print_ui_url.py").read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:{port}", helper)


if __name__ == "__main__":
    unittest.main()
