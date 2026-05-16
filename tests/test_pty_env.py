import unittest
from unittest.mock import patch

from pty_env import terminal_env


class PtyEnvTests(unittest.TestCase):
    def test_terminal_env_advertises_color_capability(self) -> None:
        with patch.dict("os.environ", {"NO_COLOR": "1", "PATH": "/bin"}, clear=True):
            env = terminal_env(cols=120, rows=40)

        self.assertEqual(env["TERM"], "xterm-256color")
        self.assertEqual(env["COLORTERM"], "truecolor")
        self.assertEqual(env["CLICOLOR"], "1")
        self.assertEqual(env["FORCE_COLOR"], "1")
        self.assertEqual(env["COLUMNS"], "120")
        self.assertEqual(env["LINES"], "40")
        self.assertNotIn("NO_COLOR", env)
        self.assertEqual(env["PATH"], "/bin")


if __name__ == "__main__":
    unittest.main()
