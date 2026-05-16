import asyncio
import unittest
from unittest.mock import MagicMock, patch

import agentrelay
from agentrelay import AdapterConfig, Config
from pty_session import PTYRegistry, PTYSession


class ActiveAgentTests(unittest.TestCase):
    def test_registry_lists_unique_alive_agents(self):
        reg = PTYRegistry()
        s1 = MagicMock(alive=True, agent_name="codex-interactive")
        s2 = MagicMock(alive=True, agent_name="codex-interactive")
        s3 = MagicMock(alive=False, agent_name="claude-interactive")
        reg._sessions = {"a": s1, "b": s2, "c": s3}

        self.assertEqual(reg.list_active_agent_names(), ["codex-interactive"])

    def test_resolve_adapter_name_respects_active_terminals(self):
        cfg = Config.load_dict({
            "node_name": "WINPC",
            "port": 9876,
            "token": "t" * 32,
            "adapters": {
                "claude-interactive": {"command": ["claude"], "mode": "interactive"},
                "codex-interactive": {"command": ["codex"], "mode": "interactive"},
            },
            "rules": [],
            "default_action": "approve",
        })

        self.assertIsNone(
            cfg.resolve_adapter_name(
                "claude", prefer_interactive=True,
                active_agents=["codex-interactive"],
            ))
        self.assertEqual(
            cfg.resolve_adapter_name(
                "codex", prefer_interactive=True,
                active_agents=["codex-interactive"],
            ),
            "codex-interactive",
        )

    def test_spawn_interactive_errors_when_agent_not_running(self):
        adapter = AdapterConfig(
            name="claude-interactive",
            command=["claude"],
            mode="interactive",
        )

        async def run_test():
            with patch.object(agentrelay, "list_active_agent_names",
                              return_value=["codex-interactive"]):
                with patch.object(agentrelay, "_deliver_prompt_to_pty",
                                  return_value=False):
                    with patch.object(agentrelay.platform, "system",
                                      return_value="Darwin"):
                        return await agentrelay._spawn_interactive_visible(
                            adapter, "hello", 1)

        result = asyncio.run(run_test())

        self.assertEqual(result["status"], "error")
        self.assertIn("not running", result["stderr"])
        self.assertIn("codex-interactive", result["stderr"])


if __name__ == "__main__":
    unittest.main()
