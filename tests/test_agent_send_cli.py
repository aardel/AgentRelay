import importlib.machinery
import importlib.util
import pathlib
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("agent_send", str(ROOT / "agent-send"))
SPEC = importlib.util.spec_from_loader("agent_send", LOADER)
agent_send = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent_send)


class AgentSendCliTests(unittest.TestCase):
    def test_parse_target_preserves_existing_node_and_agent_option(self):
        node, agent = agent_send.parse_target("WINPC", "codex")

        self.assertEqual(node, "WINPC")
        self.assertEqual(agent, "codex")

    def test_parse_target_accepts_agent_at_node(self):
        node, agent = agent_send.parse_target("codex-visible@WINPC", None)

        self.assertEqual(node, "WINPC")
        self.assertEqual(agent, "codex-visible")

    def test_parse_target_rejects_conflicting_agent_names(self):
        with self.assertRaisesRegex(ValueError, "conflicts"):
            agent_send.parse_target("claude@WINPC", "codex")

    def test_resolve_target_uses_localhost_for_local_alias(self):
        cfg = {"node_name": "WINPC", "port": 9876}

        addr, port = agent_send.resolve_target_address(
            "local", cfg, {"MAC": ("192.168.1.10", 9876)})

        self.assertEqual((addr, port), ("127.0.0.1", 9876))

    def test_resolve_target_uses_localhost_for_configured_node_name(self):
        cfg = {"node_name": "WINPC", "port": 9988}

        addr, port = agent_send.resolve_target_address(
            "WINPC", cfg, {"WINPC": ("192.168.1.186", 9876)})

        self.assertEqual((addr, port), ("127.0.0.1", 9988))

    def test_resolve_target_keeps_remote_peer_lookup(self):
        cfg = {"node_name": "WINPC", "port": 9876}

        addr, port = agent_send.resolve_target_address(
            "MAC", cfg, {"MAC": ("192.168.1.10", 9988)})

        self.assertEqual((addr, port), ("192.168.1.10", 9988))

    def test_agent_option_accepts_configured_adapter_names(self):
        argv = ["agent-send", "mac", "--agent", "codex-live", "hello"]

        def close_coroutine(coro):
            coro.close()
            return 0

        with patch("sys.argv", argv), patch.object(
            agent_send, "load_config",
            return_value={"token": "x" * 32, "node_name": "WINPC", "port": 9876},
        ):
            with patch.object(agent_send.asyncio, "run", side_effect=close_coroutine) as run:
                with self.assertRaises(SystemExit) as exit_info:
                    agent_send.main()

        self.assertEqual(exit_info.exception.code, 0)
        self.assertTrue(run.called)

    def test_agent_at_node_cli_sets_agent_without_breaking_send(self):
        argv = ["agent-send", "codex@mac", "hello"]
        captured = {}

        def close_coroutine(coro):
            captured["target"] = coro.cr_frame.f_locals["target"]
            captured["agent"] = coro.cr_frame.f_locals["agent"]
            coro.close()
            return 0

        with patch("sys.argv", argv), patch.object(
            agent_send, "load_config",
            return_value={"token": "x" * 32, "node_name": "WINPC", "port": 9876},
        ):
            with patch.object(agent_send.asyncio, "run", side_effect=close_coroutine) as run:
                with self.assertRaises(SystemExit) as exit_info:
                    agent_send.main()

        self.assertEqual(exit_info.exception.code, 0)
        self.assertTrue(run.called)
        self.assertEqual(captured["target"], "mac")
        self.assertEqual(captured["agent"], "codex")

    def test_cmd_send_posts_to_localhost_for_local_target(self):
        async def run_test():
            cfg = {"node_name": "WINPC", "port": 9876}
            fake_response = AsyncMock()
            fake_response.json.return_value = {"exit_code": 0}
            fake_post = MagicMock()
            fake_post.__aenter__.return_value = fake_response
            fake_session = MagicMock()
            fake_session.post.return_value = fake_post
            fake_session.__aenter__.return_value = fake_session

            with patch.object(agent_send, "discover", AsyncMock(return_value={})):
                with patch.object(agent_send.aiohttp, "ClientSession", return_value=fake_session):
                    with patch("builtins.print"):
                        rc = await agent_send.cmd_send(
                            "token", "local", "hello", "codex", None, cfg)

            self.assertEqual(rc, 0)
            self.assertEqual(
                fake_session.post.call_args.args[0],
                "http://127.0.0.1:9876/dispatch",
            )
            self.assertEqual(fake_session.post.call_args.kwargs["json"]["agent"], "codex")

        agent_send.asyncio.run(run_test())

    def test_parse_agents_csv_trims_agent_names(self):
        self.assertEqual(
            agent_send.parse_agents_csv("claude, codex-visible,, gemini"),
            ["claude", "codex-visible", "gemini"],
        )

    def test_cmd_coordinate_local_posts_to_local_coordinate(self):
        async def run_test():
            cfg = {"node_name": "WINPC", "port": 9876}
            fake_response = AsyncMock()
            fake_response.json.return_value = {"agent_results": []}
            fake_post = MagicMock()
            fake_post.__aenter__.return_value = fake_response
            fake_session = MagicMock()
            fake_session.post.return_value = fake_post
            fake_session.__aenter__.return_value = fake_session

            with patch.object(agent_send.aiohttp, "ClientSession", return_value=fake_session):
                with patch("builtins.print"):
                    rc = await agent_send.cmd_coordinate_local(
                        "token", "compare approaches", ["claude", "codex"], None, "parallel", cfg)

            self.assertEqual(rc, 0)
            self.assertEqual(
                fake_session.post.call_args.args[0],
                "http://127.0.0.1:9876/coordinate",
            )
            payload = fake_session.post.call_args.kwargs["json"]
            self.assertEqual(payload["agents"], [
                {"node": "WINPC", "agent": "claude"},
                {"node": "WINPC", "agent": "codex"},
            ])
            self.assertEqual(payload["coordinator_agent"], None)

        agent_send.asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
