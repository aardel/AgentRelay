import pathlib
import unittest

from aiohttp.test_utils import make_mocked_request

from agentrelay import AdapterConfig, AgentRelay, Config


ROOT = pathlib.Path(__file__).resolve().parents[1]


def make_config(token: str = "x" * 32) -> Config:
    return Config(
        node_name="WINPC",
        port=9876,
        token=token,
        adapters={
            "claude": AdapterConfig(name="claude", command=["claude", "-p", "{prompt}"]),
        },
        rules=[],
        default_action="approve",
        default_agent="claude",
        approve_timeout=300,
        use_tmux=False,
        wait_before_send_seconds=5,
        trusted_peers=[],
    )


class TerminalWebSocketAuthTests(unittest.TestCase):
    def test_terminal_auth_accepts_query_token_for_browser_websockets(self):
        relay = AgentRelay(make_config(token="secret-token-for-terminal"))
        request = make_mocked_request("GET", "/terminal?token=secret-token-for-terminal")

        self.assertTrue(relay._auth(request))

    def test_terminal_panes_send_token_in_websocket_query_string(self):
        for filename in ("terminal_pane.py", "terminal_pane_unix.py"):
            source = (ROOT / filename).read_text(encoding="utf-8")

            with self.subTest(filename=filename):
                self.assertIn("encodeURIComponent(TOKEN)", source)
                self.assertIn("?token=${encodeURIComponent(TOKEN)}", source)
                self.assertNotIn("headers: { \"X-Agent-Token\": TOKEN }", source)


if __name__ == "__main__":
    unittest.main()
