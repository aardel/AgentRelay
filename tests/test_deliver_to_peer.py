import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from agentrelay import AdapterConfig, Config
from relay_client import (
    _looks_interactive,
    deliver_to_peer,
    forward_to_peer,
    resolve_peer_agent_from_info,
    send_to_peer,
)


def _cfg() -> Config:
    return Config(
        node_name="MAC",
        port=9876,
        token="x" * 32,
        adapters={
            "codex-interactive": AdapterConfig(
                name="codex-interactive",
                command=["codex"],
                mode="interactive",
            ),
        },
        rules=[],
        default_action="approve",
        default_agent="codex-interactive",
        approve_timeout=300,
        use_tmux=False,
        wait_before_send_seconds=0,
        trusted_peers=[],
    )


def _mock_run_returns(*values):
    pending = iter(values)

    def _fake_run(awaitable):
        close = getattr(awaitable, "close", None)
        if close:
            close()
        return next(pending)

    return _fake_run


class DeliverToPeerTests(unittest.TestCase):
    def test_looks_interactive_by_mode_and_suffix(self):
        self.assertTrue(_looks_interactive("codex", "interactive"))
        self.assertTrue(_looks_interactive("codex-interactive", None))
        self.assertTrue(_looks_interactive("codex-visible", None))
        self.assertFalse(_looks_interactive("codex", "headless"))

    def test_deliver_to_peer_uses_forward_for_interactive_agent(self):
        cfg = _cfg()
        with patch("relay_client._run") as run:
            run.side_effect = _mock_run_returns(
                ("codex-interactive", "interactive", {"active_agents": ["codex-interactive"]}),
                (200, {"ok": True, "status": "queued"}),
            )
            ok, msg = deliver_to_peer(
                cfg, "192.168.1.186", 9876, "hello", "codex-interactive")
        self.assertTrue(ok)
        self.assertIn("queued", msg.lower())

    def test_deliver_to_peer_uses_dispatch_for_headless_agent(self):
        cfg = _cfg()
        with patch("relay_client._run") as run:
            run.side_effect = _mock_run_returns(
                ("codex", "headless", {}),
                (200, {"exit_code": 0, "stdout": "done"}),
            )
            ok, msg = deliver_to_peer(cfg, "192.168.1.186", 9876, "hello", "codex")
        self.assertTrue(ok)
        self.assertEqual(msg, "done")

    def test_resolve_peer_agent_limits_to_active_when_reported(self):
        info = {
            "adapters": {
                "claude-interactive": {"mode": "interactive"},
                "codex-interactive": {"mode": "interactive"},
            },
            "active_agents": ["codex-interactive"],
        }

        resolved, mode = resolve_peer_agent_from_info(info, "claude")

        self.assertEqual(resolved, "claude")
        self.assertEqual(mode, None)

    def test_resolve_peer_agent_maps_base_to_active_interactive(self):
        info = {
            "adapters": {
                "codex": {"mode": "headless"},
                "codex-interactive": {"mode": "interactive"},
            },
            "active_agents": ["codex-interactive"],
        }

        resolved, mode = resolve_peer_agent_from_info(info, "codex")

        self.assertEqual(resolved, "codex-interactive")
        self.assertEqual(mode, "interactive")

    def test_deliver_to_peer_rejects_inactive_remote_agent(self):
        cfg = _cfg()
        with patch("relay_client._run") as run:
            run.side_effect = _mock_run_returns(
                ("claude-interactive", "interactive", {
                    "active_agents": ["codex-interactive"],
                }),
            )
            ok, msg = deliver_to_peer(cfg, "192.168.1.186", 9876, "hello", "claude")

        self.assertFalse(ok)
        self.assertIn("not running", msg.lower())
        self.assertIn("codex-interactive", msg)

    def test_resolve_peer_agent_prefers_interactive_sibling_for_base_name(self):
        info = {
            "adapters": {
                "codex": {"mode": "headless"},
                "codex-interactive": {"mode": "interactive"},
            },
        }

        resolved, mode = resolve_peer_agent_from_info(info, "codex")

        self.assertEqual(resolved, "codex-interactive")
        self.assertEqual(mode, "interactive")

    def test_resolve_peer_agent_preserves_explicit_headless_when_no_sibling(self):
        info = {"adapters": {"codex": {"mode": "headless"}}}

        resolved, mode = resolve_peer_agent_from_info(info, "codex")

        self.assertEqual(resolved, "codex")
        self.assertEqual(mode, "headless")

    def test_deliver_to_peer_forwards_to_resolved_interactive_sibling(self):
        cfg = _cfg()
        with patch("relay_client._run") as run:
            run.side_effect = _mock_run_returns(
                ("codex-interactive", "interactive", {"active_agents": ["codex-interactive"]}),
                (200, {"ok": True, "status": "sent"}),
            )
            ok, msg = deliver_to_peer(cfg, "192.168.1.186", 9876, "hello", "codex")

        self.assertTrue(ok)
        self.assertIn("sent", msg.lower())

    def test_forward_to_peer_requires_ok_flag(self):
        cfg = _cfg()
        with patch("relay_client._run", side_effect=_mock_run_returns(
            (200, {"ok": False, "error": "no window"}))):
            ok, msg = forward_to_peer(
                cfg, "192.168.1.186", 9876, "hi", "codex-interactive")
        self.assertFalse(ok)
        self.assertIn("no window", msg)

    def test_forward_to_peer_rejects_byte_count_mismatch(self):
        cfg = _cfg()
        with patch("relay_client._run", side_effect=_mock_run_returns(
            (200, {"ok": True, "status": "sent", "forwarded_byte_count": 2}))):
            ok, msg = forward_to_peer(
                cfg, "192.168.1.186", 9876, "hello", "codex-interactive")

        self.assertFalse(ok)
        self.assertIn("Truncated", msg)

    def test_send_to_peer_posts_dispatch_payload(self):
        cfg = _cfg()

        async def _post():
            return 200, {"exit_code": 0, "status": "ok"}

        with patch("relay_client._run", side_effect=_mock_run_returns(
            (200, {"exit_code": 0}))):
            ok, _ = send_to_peer(cfg, "127.0.0.1", 9876, "ping", "codex")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
