"""Skills API routes."""

import unittest

from aiohttp.test_utils import TestClient, TestServer

from agentrelay import AgentRelay, Config


def _minimal_cfg() -> Config:
    return Config.load_dict({
        "node_name": "testnode",
        "port": 9876,
        "token": "test-token-12345678901234567890",
        "adapters": {"claude": {"command": ["echo", "{prompt}"], "timeout": 5}},
        "rules": [],
        "default_action": "approve",
        "use_tmux": False,
        "relay": {"wait_before_send_seconds": 3},
    })


class SkillsApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.relay = AgentRelay(_minimal_cfg())
        self.app = self.relay.build_app()
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.headers = {"X-Agent-Token": "test-token-12345678901234567890"}

    async def asyncTearDown(self) -> None:
        await self.client.close()

    async def test_skills_list(self) -> None:
        resp = await self.client.get("/api/skills", headers=self.headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertIn("skills", data)
        self.assertTrue(any(s["name"] == "relay-send" for s in data["skills"]))


if __name__ == "__main__":
    unittest.main()
