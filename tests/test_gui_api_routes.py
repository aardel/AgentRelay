"""GUI API routes on the aiohttp app."""

import unittest

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


if __name__ == "__main__":
    unittest.main()
