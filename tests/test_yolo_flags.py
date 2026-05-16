"""YOLO flag injection for PTY launches."""

import unittest

from agentrelay import AdapterConfig
from relay_client import interactive_launch_argv
from yolo_flags import apply_yolo_flags, detect_agent_family, yolo_supported


class YoloFlagsTests(unittest.TestCase):
    def test_detect_claude(self) -> None:
        self.assertEqual(detect_agent_family("claude", ["claude"]), "claude")

    def test_apply_yolo_claude(self) -> None:
        argv = apply_yolo_flags(["claude"], "claude", True)
        self.assertIn("--dangerously-skip-permissions", argv)

    def test_apply_yolo_codex(self) -> None:
        argv = apply_yolo_flags(["codex"], "codex-visible", True)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", argv)

    def test_yolo_off_unchanged(self) -> None:
        argv = ["codex"]
        self.assertEqual(apply_yolo_flags(argv, "codex", False), argv)

    def test_interactive_launch_with_yolo(self) -> None:
        adapter = AdapterConfig(name="claude", command=["claude"], mode="interactive")
        argv = interactive_launch_argv("claude", adapter, yolo=True)
        self.assertEqual(argv[0], "claude")
        self.assertIn("--dangerously-skip-permissions", argv)

    def test_yolo_supported(self) -> None:
        self.assertTrue(yolo_supported("claude", ["claude"]))
        self.assertFalse(yolo_supported("unknown-tool", ["foo"]))


if __name__ == "__main__":
    unittest.main()
