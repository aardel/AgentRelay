import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from agentrelay import AdapterConfig, Config
from relay_client import (
    _looks_interactive,
    deliver_to_peer,
    forward_to_peer,
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


class DeliverToPeerTests(unittest.TestCase):
    def test_looks_interactive_by_mode_and_suffix(self):
        self.assertTrue(_looks_interactive("codex", "interactive"))
        self.assertTrue(_looks_interactive("codex-interactive", None))
        self.assertTrue(_looks_interactive("codex-visible", None))
        self.assertFalse(_looks_interactive("codex", "headless"))

    def test_deliver_to_peer_uses_forward_for_interactive_agent(self):
        cfg = _cfg()
        with patch("relay_client._run") as run:
            run.side_effect = [
                "interactive",
                (200, {"ok": True, "status": "queued"}),
            ]
            ok, msg = deliver_to_peer(
                cfg, "192.168.1.186", 9876, "hello", "codex-interactive")
        self.assertTrue(ok)
        self.assertIn("queued", msg.lower())

    def test_deliver_to_peer_uses_dispatch_for_headless_agent(self):
        cfg = _cfg()
        with patch("relay_client._run") as run:
            run.side_effect = [
                "headless",
                (200, {"exit_code": 0, "stdout": "done"}),
            ]
            ok, msg = deliver_to_peer(cfg, "192.168.1.186", 9876, "hello", "codex")
        self.assertTrue(ok)
        self.assertEqual(msg, "done")

    def test_forward_to_peer_requires_ok_flag(self):
        cfg = _cfg()
        with patch("relay_client._run", return_value=(200, {"ok": False, "error": "no window"})):
            ok, msg = forward_to_peer(
                cfg, "192.168.1.186", 9876, "hi", "codex-interactive")
        self.assertFalse(ok)
        self.assertIn("no window", msg)

    def test_send_to_peer_posts_dispatch_payload(self):
        cfg = _cfg()

        async def _post():
            return 200, {"exit_code": 0, "status": "ok"}

        with patch("relay_client._run", side_effect=[(200, {"exit_code": 0})]):
            ok, _ = send_to_peer(cfg, "127.0.0.1", 9876, "ping", "codex")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
