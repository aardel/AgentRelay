"""AgentRelay skill installation helpers."""

import tempfile
import signal
import unittest
from pathlib import Path
from unittest.mock import patch

import relay_client


class RelayClientSkillsTests(unittest.TestCase):
    def test_codex_skill_installs_as_skill_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_skills = root / "codex-skills"
            with patch.dict(relay_client.SKILL_TARGETS, {"Codex": codex_skills}):
                msg = relay_client.install_skill("relay-send", root, "Codex")

                self.assertEqual(msg, "Installed /relay-send for Codex")
                skill_path = codex_skills / "relay-send" / "SKILL.md"
                self.assertTrue(skill_path.exists())
                text = skill_path.read_text(encoding="utf-8")
                self.assertIn('name: "relay-send"', text)
                self.assertIn("description:", text)
                self.assertIn("agent-send", text)
                self.assertTrue(relay_client.is_skill_installed("relay-send", "Codex"))

    def test_codex_remove_cleans_skill_and_legacy_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_skills = root / "codex-skills"
            legacy_commands = root / "codex-commands"
            legacy_commands.mkdir()
            (legacy_commands / "relay-send.md").write_text("legacy", encoding="utf-8")
            with (
                patch.dict(relay_client.SKILL_TARGETS, {"Codex": codex_skills}),
                patch.object(relay_client, "LEGACY_CODEX_COMMANDS_DIR", legacy_commands),
            ):
                relay_client.install_skill("relay-send", root, "Codex")
                msg = relay_client.remove_skill("relay-send", "Codex")

                self.assertEqual(msg, "Removed /relay-send from Codex")
                self.assertFalse((codex_skills / "relay-send" / "SKILL.md").exists())
                self.assertFalse((legacy_commands / "relay-send.md").exists())

    def test_stop_relay_uses_daemon_pid_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "agentrelay.pid"
            pid_path.write_text("12345", encoding="utf-8")
            relay_client._daemon_proc = None

            with (
                patch.object(relay_client, "pid_file_path", return_value=pid_path),
                patch("os.kill") as kill,
            ):
                relay_client.stop_relay(object())

            kill.assert_called_once_with(12345, signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
