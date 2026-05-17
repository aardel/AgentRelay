"""Tests for optional agentmemory sidecar bridge."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from agentmemory_bridge import (
    AgentmemoryConfig,
    format_recall_markdown,
    observe_session_end,
    strip_ansi,
)


class AgentmemoryBridgeTests(unittest.TestCase):
    def test_format_recall_markdown_respects_budget(self) -> None:
        results = [{"content": "x" * 500} for _ in range(20)]
        text = format_recall_markdown(results, token_budget=200)
        self.assertIn("Project memory", text)
        self.assertLess(len(text), 2000)

    def test_strip_ansi(self) -> None:
        raw = "\x1b[31mhello\x1b[0m world"
        self.assertEqual(strip_ansi(raw), "hello world")

    def test_config_from_dict_reads_env_secret(self) -> None:
        with patch.dict("os.environ", {"AGENTMEMORY_SECRET": "sekrit"}):
            cfg = AgentmemoryConfig.from_dict({"enabled": True})
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.secret, "sekrit")


class AgentmemoryBridgeAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_recall_context_parses_results(self) -> None:
        from agentmemory_bridge import fetch_recall_context

        cfg = AgentmemoryConfig(enabled=True, inject_on_launch=True)
        payload = {"results": [{"content": "JWT uses jose middleware"}]}

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=payload)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("agentmemory_bridge.aiohttp.ClientSession", return_value=mock_session):
            text = await fetch_recall_context(cfg, query="auth", agent_id="claude")

        self.assertIn("JWT uses jose", text)

    async def test_observe_session_end_posts_payload(self) -> None:
        cfg = AgentmemoryConfig(enabled=True, observe_on_close=True)

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value="")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("agentmemory_bridge.aiohttp.ClientSession", return_value=mock_session):
            await observe_session_end(
                cfg,
                agent_id="claude-interactive",
                session_id="abc",
                reason="process_exited",
                scrollback=b"output line\n",
                node_name="WINPC",
                uptime_seconds=42.0,
            )

        mock_session.post.assert_called_once()
        args, kwargs = mock_session.post.call_args
        self.assertIn("/agentmemory/observe", args[0])
        self.assertEqual(kwargs["json"]["project"], "agentrelay")


if __name__ == "__main__":
    unittest.main()
