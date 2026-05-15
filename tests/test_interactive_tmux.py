import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import agentrelay
from agentrelay import AdapterConfig, Config


class InteractiveTmuxTests(unittest.TestCase):
    def test_adapter_config_loads_interactive_tmux_fields(self):
        cfg = Config.load_dict({
            "node_name": "node",
            "port": 9876,
            "token": "x" * 32,
            "relay": {"wait_before_send_seconds": 5},
            "trusted_peers": [],
            "adapters": {
                "codex-visible": {
                    "mode": "interactive",
                    "session": "agentrelay-codex",
                    "command": ["codex"],
                    "timeout": 1800,
                }
            },
        })

        adapter = cfg.adapters["codex-visible"]

        self.assertEqual(adapter.mode, "interactive")
        self.assertEqual(adapter.session, "agentrelay-codex")
        self.assertEqual(adapter.command, ["codex"])

    def test_interactive_tmux_sends_prompt_to_existing_session(self):
        adapter = AdapterConfig(
            name="codex-visible",
            command=["codex"],
            mode="interactive",
            session="agentrelay-codex",
        )
        cfg = Config(
            node_name="node",
            port=9876,
            token="x" * 32,
            adapters={"codex-visible": adapter},
            rules=[],
            default_action="approve",
            default_agent="codex-visible",
            approve_timeout=300,
            use_tmux=False,
            wait_before_send_seconds=5,
            trusted_peers=[],
        )

        async def run_test():
            with patch.object(agentrelay.shutil, "which", return_value="/usr/bin/tmux"):
                with patch.object(agentrelay, "run_subprocess", new=AsyncMock(
                    return_value={"status": "ok", "exit_code": 0, "stdout": "", "stderr": ""}
                )) as run_subprocess:
                    with patch.object(asyncio, "sleep", new=AsyncMock()):
                        result = await agentrelay.spawn_agent(cfg, adapter, "hello world")

            self.assertEqual(run_subprocess.await_count, 3)
            run_subprocess.assert_any_await(
                ["tmux", "has-session", "-t", "agentrelay-codex"], timeout=5)
            run_subprocess.assert_any_await(
                ["tmux", "send-keys", "-t", "agentrelay-codex", "hello world"], timeout=10)
            run_subprocess.assert_any_await(
                ["tmux", "send-keys", "-t", "agentrelay-codex", "", "Enter"], timeout=10)
            self.assertEqual(result["status"], "sent")
            self.assertIn("agentrelay-codex", result["stdout"])

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
