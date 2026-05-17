"""GUI API routes on the aiohttp app."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import TestClient, TestServer

from agentrelay import AgentRelay, Config
from agent_data import AgentDataStore
from pty_session import PTYSession, pty_registry


def _minimal_cfg() -> Config:
    return Config.load_dict({
        "node_name": "testnode",
        "port": 9876,
        "token": "test-token-12345678901234567890",
        "adapters": {
            "claude": {
                "command": [sys.executable, "-c", "pass"],
                "timeout": 5,
            },
        },
        "rules": [],
        "default_action": "approve",
        "use_tmux": False,
        "relay": {"wait_before_send_seconds": 3},
    })


class GuiApiRoutesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.relay = AgentRelay(_minimal_cfg())
        self.relay.agent_data = AgentDataStore(Path(self.tmp.name))
        self.app = self.relay.build_app()
        self.server = TestServer(self.app)
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        await self.client.close()
        pty_registry._sessions.clear()
        self.tmp.cleanup()

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
        self.assertIn("agents", data)
        self.assertIn("agents_missing", data)
        self.assertEqual(data["agents"][0]["id"], "claude")

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
        self.assertEqual(data["byte_count"], len("hello".encode("utf-8")))
        self.assertEqual(
            data["forwarded_byte_count"],
            len("[Forwarded from codex on WINPC]\n\nhello".encode("utf-8")),
        )
        self.assertEqual(spawned.await_args.args[1].name, "gemini-interactive")

    async def test_resume_and_memory_routes(self) -> None:
        headers = {"X-Agent-Token": "test-token-12345678901234567890"}

        resp = await self.client.post(
            "/api/agents/claude/resume",
            headers=headers,
            json={"resume": "# Claude"},
        )
        self.assertEqual(resp.status, 200)

        resp = await self.client.get("/api/agents/claude/resume", headers=headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["resume"], "# Claude")

        resp = await self.client.post(
            "/api/agents/claude/memory",
            headers=headers,
            json={"memory": {"project": "AgentRelay"}},
        )
        self.assertEqual(resp.status, 200)

        resp = await self.client.get("/api/agents/claude/memory", headers=headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["memory"], {"project": "AgentRelay"})

    async def test_memory_route_rejects_non_object(self) -> None:
        headers = {"X-Agent-Token": "test-token-12345678901234567890"}
        resp = await self.client.post(
            "/api/agents/claude/memory",
            headers=headers,
            json={"memory": ["bad"]},
        )
        self.assertEqual(resp.status, 400)

    async def test_terminal_usage_route(self) -> None:
        headers = {"X-Agent-Token": "test-token-12345678901234567890"}
        session = PTYSession(agent_name="claude", node="testnode")
        session.usage.observe_text("tokens used: 12k context 200k")
        pty_registry.register(session)

        resp = await self.client.get(
            f"/api/terminal/sessions/{session.session_id}/usage",
            headers=headers,
        )

        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["session_id"], session.session_id)
        self.assertEqual(data["used"], 12000)
        self.assertEqual(data["limit"], 200000)
        self.assertEqual(data["remaining"], 188000)

    async def test_terminal_usage_route_missing_session(self) -> None:
        headers = {"X-Agent-Token": "test-token-12345678901234567890"}
        resp = await self.client.get(
            "/api/terminal/sessions/missing/usage",
            headers=headers,
        )
        self.assertEqual(resp.status, 404)

    async def test_terminal_usage_refresh_sends_claude_usage_command(self) -> None:
        class FakePty:
            alive = True

            def __init__(self) -> None:
                self.writes: list[str] = []

            async def write(self, data: str) -> None:
                self.writes.append(data)

        headers = {"X-Agent-Token": "test-token-12345678901234567890"}
        session = PTYSession(agent_name="claude-interactive", node="testnode")
        fake_pty = FakePty()
        session._pty = fake_pty
        pty_registry.register(session)

        resp = await self.client.post(
            f"/api/terminal/sessions/{session.session_id}/usage/refresh",
            headers=headers,
        )

        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(fake_pty.writes, ["/usage\r"])

    async def test_terminal_usage_refresh_rejects_non_claude_session(self) -> None:
        headers = {"X-Agent-Token": "test-token-12345678901234567890"}
        session = PTYSession(agent_name="codex-interactive", node="testnode")
        pty_registry.register(session)

        resp = await self.client.post(
            f"/api/terminal/sessions/{session.session_id}/usage/refresh",
            headers=headers,
        )

        self.assertEqual(resp.status, 400)


if __name__ == "__main__":
    unittest.main()
