"""GUI API routes on the aiohttp app."""

import unittest
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import TestClient, TestServer

from agentrelay import AgentRelay, Config


def _minimal_cfg() -> Config:
    return Config.load_dict({
        "node_name": "testnode",
        "port": 9876,
        "token": "test-token-12345678901234567890",
        "adapters": {
            "claude": {"command": ["echo", "{prompt}"], "timeout": 5},
        },
        "rules": [],
        "default_action": "approve",
        "use_tmux": False,
        "relay": {"wait_before_send_seconds": 3},
    })


class GuiApiRoutesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.relay = AgentRelay(_minimal_cfg())
        self.app = self.relay.build_app()
        self.server = TestServer(self.app)
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        await self.client.close()

    async def test_gui_index_served(self) -> None:
        resp = await self.client.get("/")
        self.assertEqual(resp.status, 200)
        text = await resp.text()
        self.assertIn("AgentRelay", text)

    async def test_api_status_requires_token(self) -> None:
        resp = await self.client.get("/api/status")
        self.assertEqual(resp.status, 401)

    async def test_api_status_with_token(self) -> None:
        headers = {"X-Agent-Token": "test-token-12345678901234567890"}
        resp = await self.client.get("/api/status", headers=headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["node"], "testnode")
        self.assertTrue(data["relay_running"])

    async def test_forward_resolves_base_agent_to_interactive_sibling(self) -> None:
        cfg = Config.load_dict({
            "node_name": "testnode",
            "port": 9876,
            "token": "test-token-12345678901234567890",
            "adapters": {
                "gemini": {
                    "command": ["gemini", "-p", "{prompt}"],
                    "mode": "headless",
                    "timeout": 5,
                },
                "gemini-interactive": {
                    "command": ["gemini"],
                    "mode": "interactive",
                    "timeout": 5,
                },
            },
            "rules": [],
            "default_action": "approve",
            "use_tmux": False,
            "relay": {"wait_before_send_seconds": 1},
        })
        relay = AgentRelay(cfg)
        app = relay.build_app()
        server = TestServer(app)
        client = TestClient(server)
        await client.start_server()
        self.addAsyncCleanup(client.close)

        with patch("agentrelay.spawn_agent", new=AsyncMock(return_value={
            "status": "sent",
            "exit_code": 0,
            "stdout": "sent",
            "stderr": "",
        })) as spawned:
            resp = await client.post("/forward", headers={
                "X-Agent-Token": "test-token-12345678901234567890",
            }, json={
                "from_node": "WINPC",
                "from_agent": "codex",
                "to_agent": "gemini",
                "message": "hello",
            })

        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["requested_agent"], "gemini")
        self.assertEqual(data["resolved_agent"], "gemini-interactive")
        self.assertEqual(spawned.await_args.args[1].name, "gemini-interactive")


if __name__ == "__main__":
    unittest.main()
