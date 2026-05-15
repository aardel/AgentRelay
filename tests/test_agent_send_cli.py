import importlib.machinery
import importlib.util
import pathlib
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("agent_send", str(ROOT / "agent-send"))
SPEC = importlib.util.spec_from_loader("agent_send", LOADER)
agent_send = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent_send)


class AgentSendCliTests(unittest.TestCase):
    def test_agent_option_accepts_configured_adapter_names(self):
        argv = ["agent-send", "mac", "--agent", "codex-live", "hello"]

        def close_coroutine(coro):
            coro.close()
            return 0

        with patch("sys.argv", argv), patch.object(agent_send, "load_token", return_value="x" * 32):
            with patch.object(agent_send.asyncio, "run", side_effect=close_coroutine) as run:
                with self.assertRaises(SystemExit) as exit_info:
                    agent_send.main()

        self.assertEqual(exit_info.exception.code, 0)
        self.assertTrue(run.called)


if __name__ == "__main__":
    unittest.main()
