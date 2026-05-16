"""PTY launch argv builder."""

import unittest

from agentrelay import AdapterConfig
from relay_client import interactive_launch_argv


class InteractiveLaunchArgvTests(unittest.TestCase):
    def test_interactive_adapter_uses_full_command(self) -> None:
        adapter = AdapterConfig(
            name="codex-visible",
            command=["codex"],
            mode="interactive",
        )
        self.assertEqual(interactive_launch_argv("codex-visible", adapter), ["codex"])

    def test_headless_strips_prompt_flags(self) -> None:
        adapter = AdapterConfig(
            name="claude",
            command=["claude", "-p", "{prompt}"],
            mode="headless",
        )
        self.assertEqual(interactive_launch_argv("claude", adapter), ["claude"])

    def test_codex_exec_strips_exec_and_prompt(self) -> None:
        adapter = AdapterConfig(
            name="codex",
            command=["codex", "exec", "--skip-git-repo-check", "{prompt}"],
            mode="headless",
        )
        self.assertEqual(
            interactive_launch_argv("codex", adapter),
            ["codex", "--skip-git-repo-check"],
        )


if __name__ == "__main__":
    unittest.main()
