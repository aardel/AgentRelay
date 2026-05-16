import unittest

from agentrelay_app import build_prompt_targets, resolve_prompt_target


class AgentRelayAppTargetTests(unittest.TestCase):
    def test_build_prompt_targets_includes_local_agents_first(self):
        data = {
            "node": "WINPC",
            "agents": [
                {"id": "claude", "label": "Claude"},
                {"id": "codex", "label": "Codex"},
            ],
            "nearby": [
                {
                    "name": "MAC",
                    "address": "192.168.1.10",
                    "port": 9876,
                    "connected": True,
                    "agents": "codex,gemini",
                }
            ],
        }

        targets = build_prompt_targets(data, local_port=9988)

        self.assertEqual(targets[0]["name"], "This computer (WINPC, use @local)")
        self.assertEqual(targets[0]["address"], "127.0.0.1")
        self.assertEqual(targets[0]["port"], 9988)
        self.assertEqual(targets[0]["_agents_list"], ["claude", "codex"])
        self.assertEqual(targets[1]["name"], "MAC")
        self.assertEqual(targets[1]["address"], "192.168.1.10")
        self.assertEqual(targets[1]["_agents_list"], ["codex", "gemini"])

    def test_build_prompt_targets_excludes_unconnected_remote_peers(self):
        data = {
            "node": "WINPC",
            "agents": [{"id": "claude", "label": "Claude"}],
            "nearby": [
                {
                    "name": "MAC",
                    "address": "192.168.1.10",
                    "port": 9876,
                    "connected": False,
                    "agents": "codex",
                }
            ],
        }

        targets = build_prompt_targets(data, local_port=9876)

        self.assertEqual([target["name"] for target in targets], ["This computer (WINPC, use @local)"])

    def test_resolve_prompt_target_finds_display_name(self):
        targets = [
            {"name": "This computer (WINPC, use @local)", "address": "127.0.0.1", "port": 9876},
            {"name": "MAC", "address": "192.168.1.10", "port": 9876},
        ]

        target = resolve_prompt_target(targets, "MAC")

        self.assertEqual(target["address"], "192.168.1.10")


if __name__ == "__main__":
    unittest.main()
