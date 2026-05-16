import importlib.machinery
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("agent_talk", str(ROOT / "agent-talk"))
SPEC = importlib.util.spec_from_loader("agent_talk", LOADER)
agent_talk = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent_talk)


class AgentTalkCliTests(unittest.TestCase):
    def test_parse_target_preserves_legacy_to_agent_option(self):
        node, agent = agent_talk.parse_target("MAC", "codex")

        self.assertEqual(node, "MAC")
        self.assertEqual(agent, "codex")

    def test_parse_target_accepts_agent_at_node(self):
        node, agent = agent_talk.parse_target("claude@local", None)

        self.assertEqual(node, "local")
        self.assertEqual(agent, "claude")

    def test_resolve_target_address_uses_localhost_for_local(self):
        cfg = {"node_name": "WINPC", "port": 9876}

        addr, port = agent_talk.resolve_target_address("local", cfg, {})

        self.assertEqual((addr, port), ("127.0.0.1", 9876))

    def test_resolve_target_address_keeps_remote_lookup(self):
        cfg = {"node_name": "WINPC", "port": 9876}

        addr, port = agent_talk.resolve_target_address(
            "MAC", cfg, {"MAC": ("192.168.1.10", 9988)})

        self.assertEqual((addr, port), ("192.168.1.10", 9988))


if __name__ == "__main__":
    unittest.main()
