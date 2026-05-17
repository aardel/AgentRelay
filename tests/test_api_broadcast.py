"""Global broadcast API."""

import sys
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import TestClient, TestServer

from agentrelay import AgentRelay, Config, GLOBAL_BROADCAST_PREFIX


def _minimal_cfg() -> Config:
    return Config.load_dict({
        "node_name": "testnode",
        "port": 9876,
        "token": "test-token-12345678901234567890",
        "adapters": {
            "claude": {"command": [sys.executable, "-c", "print('{prompt}')"], "timeout": 5},
            "codex": {"command": [sys.executable, "-c", "print('{prompt}')"], "timeout": 5},
        },
        "rules": [],
        "default_action": "approve",
        "use_tmux": False,
        "relay": {"wait_before_send_seconds": 3},
    })


class ApiBroadcastTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.relay = AgentRelay(_minimal_cfg())
        self.app = self.relay.build_app()
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.headers = {"X-Agent-Token": "test-token-12345678901234567890"}

    async def asyncTearDown(self) -> None:
        await self.client.close()

    async def test_broadcast_local_requires_message(self) -> None:
        resp = await self.client.post(
            "/api/broadcast",
            headers=self.headers,
            json={"message": "  "},
        )
        self.assertEqual(resp.status, 400)

    async def test_broadcast_local_all_agents(self) -> None:
        with patch("agentrelay.spawn_agent", new_callable=AsyncMock) as spawn:
            spawn.return_value = {"exit_code": 0, "status": "sent", "stdout": "ok"}
            resp = await self.client.post(
                "/api/broadcast",
                headers=self.headers,
                json={"message": "hello everyone", "scope": "local"},
            )
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["global_broadcast"])
        self.assertEqual(data["sent_to"], 2)
        self.assertEqual(data["succeeded"], 2)
        self.assertEqual(spawn.await_count, 2)
        first_call_msg = spawn.call_args_list[0][0][2]
        self.assertTrue(first_call_msg.startswith(GLOBAL_BROADCAST_PREFIX))
        self.assertIn("hello everyone", first_call_msg)


if __name__ == "__main__":
    unittest.main()
