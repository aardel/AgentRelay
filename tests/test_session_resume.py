"""Tests for session-resume support.

Covers:
  1. GET /api/sessions/{agent} returns Claude session metadata sorted newest first.
  2. GET /api/sessions/{agent} returns [] for non-Claude agents.
  3. GET /api/sessions/{agent} returns [] when ~/.claude/sessions/ is missing.
  4. interactive_launch_argv injects --resume <id> for Claude-family adapters.
  5. interactive_launch_argv does NOT inject --resume for non-Claude adapters.
  6. Fresh-start path (no resume_session_id) produces argv without --resume.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentrelay import AdapterConfig, AgentRelay, Config
from agent_data import AgentDataStore
from relay_client import interactive_launch_argv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg() -> Config:
    return Config.load_dict({
        "node_name": "testnode",
        "port": 9876,
        "token": "test-token-12345678901234567890",
        "adapters": {
            "claude": {"command": [sys.executable, "-c", "pass"], "timeout": 5},
            "codex":  {"command": ["codex", "exec", "{prompt}"],  "timeout": 5},
        },
        "rules": [],
        "default_action": "approve",
        "use_tmux": False,
        "relay": {"wait_before_send_seconds": 3},
    })


def _claude_adapter() -> AdapterConfig:
    return AdapterConfig(name="claude", command=["claude", "-p", "{prompt}"], mode="headless")


def _codex_adapter() -> AdapterConfig:
    return AdapterConfig(name="codex", command=["codex", "exec", "{prompt}"], mode="headless")


# ---------------------------------------------------------------------------
# GET /api/sessions/{agent}
# ---------------------------------------------------------------------------

class ApiSessionsTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self) -> None:
        from aiohttp.test_utils import TestClient, TestServer
        from pty_session import pty_registry
        self.tmp = tempfile.TemporaryDirectory()
        agent_data_dir = Path(self.tmp.name) / "agent_data"
        agent_data_dir.mkdir()
        self.relay = AgentRelay(_cfg())
        self.relay.agent_data = AgentDataStore(agent_data_dir)
        self.app = self.relay.build_app()
        self.server = TestServer(self.app)
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        await self.client.close()
        self.tmp.cleanup()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _sessions_dir(self, home_name: str = "home") -> Path:
        d = Path(self.tmp.name) / home_name / ".claude" / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _home(self, home_name: str = "home") -> Path:
        return Path(self.tmp.name) / home_name

    @staticmethod
    def _write_session(sessions_dir: Path, session_id: str, started_at: float) -> None:
        data = {
            "sessionId": session_id,
            "startedAt": started_at,
            "cwd": "/tmp",
            "status": "completed",
            "procStart": "",
        }
        (sessions_dir / f"{session_id}.json").write_text(json.dumps(data))

    async def _get_sessions(self, agent: str, home: Path | None = None):
        from aiohttp.test_utils import TestClient
        kwargs = {"headers": {"X-Agent-Token": "test-token-12345678901234567890"}}
        if home is not None:
            with patch("pathlib.Path.home", return_value=home):
                return await self.client.get(f"/api/sessions/{agent}", **kwargs)
        return await self.client.get(f"/api/sessions/{agent}", **kwargs)

    # ── tests ─────────────────────────────────────────────────────────────────

    async def test_returns_claude_sessions_sorted_newest_first(self) -> None:
        sdir = self._sessions_dir()
        self._write_session(sdir, "aaa", started_at=1_000)
        self._write_session(sdir, "bbb", started_at=3_000)
        self._write_session(sdir, "ccc", started_at=2_000)

        resp = await self._get_sessions("claude", home=self._home())
        self.assertEqual(resp.status, 200)
        body = await resp.json()
        self.assertEqual(body["agent"], "claude")
        ids = [s["sessionId"] for s in body["sessions"]]
        self.assertEqual(ids, ["bbb", "ccc", "aaa"])

    async def test_returns_session_metadata_fields(self) -> None:
        sdir = self._sessions_dir("home2")
        self._write_session(sdir, "xyz", started_at=500)

        resp = await self._get_sessions("claude", home=self._home("home2"))
        body = await resp.json()
        s = body["sessions"][0]
        self.assertEqual(s["sessionId"], "xyz")
        self.assertIn("cwd", s)
        self.assertIn("startedAt", s)
        self.assertIn("status", s)

    async def test_returns_empty_for_non_claude_agent(self) -> None:
        resp = await self._get_sessions("codex")
        self.assertEqual(resp.status, 200)
        body = await resp.json()
        self.assertEqual(body["agent"], "codex")
        self.assertEqual(body["sessions"], [])

    async def test_returns_empty_when_sessions_dir_missing(self) -> None:
        home = Path(self.tmp.name) / "empty_home"
        home.mkdir()
        resp = await self._get_sessions("claude", home=home)
        self.assertEqual(resp.status, 200)
        body = await resp.json()
        self.assertEqual(body["sessions"], [])

    async def test_requires_auth(self) -> None:
        resp = await self.client.get("/api/sessions/claude")
        self.assertEqual(resp.status, 401)


# ---------------------------------------------------------------------------
# interactive_launch_argv resume behaviour
# ---------------------------------------------------------------------------

class ResumeArgvTests(unittest.TestCase):

    def test_claude_injects_resume_flag(self) -> None:
        argv = interactive_launch_argv("claude", _claude_adapter(), resume_session_id="abc-123")
        self.assertIn("--resume", argv)
        idx = argv.index("--resume")
        self.assertEqual(argv[idx + 1], "abc-123")

    def test_resume_flag_placed_immediately_after_executable(self) -> None:
        argv = interactive_launch_argv("claude", _claude_adapter(), resume_session_id="xyz")
        self.assertEqual(argv[0], "claude")
        self.assertEqual(argv[1], "--resume")
        self.assertEqual(argv[2], "xyz")

    def test_non_claude_adapter_does_not_inject_resume_flag(self) -> None:
        argv = interactive_launch_argv("codex", _codex_adapter(), resume_session_id="abc-123")
        self.assertNotIn("--resume", argv)

    def test_fresh_start_omits_resume_flag(self) -> None:
        argv = interactive_launch_argv("claude", _claude_adapter())
        self.assertNotIn("--resume", argv)

    def test_none_session_id_omits_resume_flag(self) -> None:
        argv = interactive_launch_argv("claude", _claude_adapter(), resume_session_id=None)
        self.assertNotIn("--resume", argv)

    def test_empty_string_session_id_omits_resume_flag(self) -> None:
        # "" is falsy — must not produce --resume <empty>
        argv = interactive_launch_argv("claude", _claude_adapter(), resume_session_id="")
        self.assertNotIn("--resume", argv)


if __name__ == "__main__":
    unittest.main()
