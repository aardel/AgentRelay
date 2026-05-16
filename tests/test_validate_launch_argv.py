import unittest

from relay_client import validate_launch_argv


class ValidateLaunchArgvTests(unittest.TestCase):
    def test_missing_executable_returns_message(self) -> None:
        err = validate_launch_argv(["definitely-not-a-real-agentrelay-binary-xyz"])
        self.assertIsNotNone(err)
        self.assertIn("not found on PATH", err)

    def test_python_is_usually_found(self) -> None:
        import sys

        err = validate_launch_argv([sys.executable, "-V"])
        self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()
