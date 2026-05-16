import unittest

from agentrelay import AdapterConfig, Config
from relay_client import build_agent_snippet


class RelayClientSnippetTests(unittest.TestCase):
    def test_snippet_lists_local_and_remote_agent_at_node_commands(self):
        cfg = Config(
            node_name="WINPC",
            port=9876,
            token="x" * 32,
            adapters={
                "claude": AdapterConfig(name="claude", command=["claude", "-p", "{prompt}"]),
                "codex": AdapterConfig(name="codex", command=["codex", "exec", "{prompt}"]),
            },
            rules=[],
            default_action="approve",
            default_agent="claude",
            approve_timeout=300,
            use_tmux=False,
            wait_before_send_seconds=5,
            trusted_peers=[],
        )

        snippet = build_agent_snippet(
            cfg,
            nearby=[{"name": "MAC", "address": "192.168.1.10", "port": 9876, "agents": ["codex"]}],
        )

        self.assertIn('agent-send claude@local "<task>"', snippet)
        self.assertIn('agent-send codex@WINPC "<task>"', snippet)
        self.assertIn('agent-send codex@MAC "<task>"', snippet)
        self.assertNotIn('--agent codex', snippet)


if __name__ == "__main__":
    unittest.main()
