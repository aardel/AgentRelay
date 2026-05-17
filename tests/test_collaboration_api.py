import sys
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import TestClient, TestServer

from agentrelay import AgentRelay, Config
from pty_session import pty_registry


TOKEN = "test-token-12345678901234567890"


def _minimal_cfg() -> Config:
    return Config.load_dict({
        "node_name": "WINPC",
        "port": 9876,
        "token": TOKEN,
        "adapters": {
            "codex-interactive": {
                "command": [sys.executable, "-c", "pass"],
                "mode": "interactive",
                "timeout": 5,
            },
            "claude-interactive": {
                "command": [sys.executable, "-c", "pass"],
                "mode": "interactive",
                "timeout": 5,
            },
        },
        "rules": [],
        "default_action": "approve",
        "use_tmux": False,
        "relay": {"wait_before_send_seconds": 3},
    })


class CollaborationApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.relay = AgentRelay(_minimal_cfg())
        self.relay.peers.upsert(
            "MAC", "192.168.1.20", 9876,
            agents="codex-interactive,gemini-interactive",
            active_agents="gemini-interactive",
        )
        self.app = self.relay.build_app()
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.headers = {"X-Agent-Token": TOKEN}

    async def asyncTearDown(self) -> None:
        await self.client.close()
        pty_registry._sessions.clear()

    async def test_targets_lists_active_local_and_remote_terminals_only(self) -> None:
        with patch("agentrelay.list_active_agent_names",
                   return_value=["codex-interactive"]):
            resp = await self.client.get(
                "/api/collaboration/targets", headers=self.headers)

        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["targets"], [
            {
                "node": "WINPC",
                "agent": "codex-interactive",
                "label": "WINPC/codex-interactive",
                "local": True,
            },
            {
                "node": "MAC",
                "agent": "gemini-interactive",
                "label": "MAC/gemini-interactive",
                "local": False,
            },
        ])

    async def test_send_shared_instruction_delivers_collaboration_prompt(self) -> None:
        with patch("agentrelay.list_active_agent_names",
                   return_value=["codex-interactive", "claude-interactive"]):
            with patch("agentrelay.spawn_agent", new_callable=AsyncMock) as spawn:
                spawn.return_value = {
                    "status": "sent",
                    "exit_code": 0,
                    "stdout": "",
                    "stderr": "",
                }
                resp = await self.client.post(
                    "/api/collaboration/send",
                    headers=self.headers,
                    json={
                        "mode": "shared",
                        "message": "Design the terminal collaboration UX.",
                        "targets": [
                            {"node": "WINPC", "agent": "codex-interactive"},
                            {"node": "WINPC", "agent": "claude-interactive"},
                        ],
                    },
                )

        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["sent_to"], 2)
        self.assertEqual(spawn.await_count, 2)
        prompt = spawn.await_args_list[0].args[2]
        self.assertIn("Collaboration session", prompt)
        self.assertIn("Mode: shared instruction", prompt)
        self.assertIn("challenge assumptions", prompt)
        self.assertIn("Design the terminal collaboration UX.", prompt)


if __name__ == "__main__":
    unittest.main()
