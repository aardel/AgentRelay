import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import agentrelay
from agentrelay import AdapterConfig
from agentrelay_app import agent_launch_script_name
from pty_session import pty_registry


class WindowsDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        agentrelay._gui_delivery_queue.clear()

    def test_interactive_queue_includes_adapter_name(self):
        adapter = AdapterConfig(
            name="codex-interactive",
            command=["codex"],
            mode="interactive",
            window_title="codex",
        )

        async def run_test():
            agentrelay._gui_delivery_queue.clear()
            with patch.object(agentrelay.platform, "system", return_value="Windows"):
                result = await agentrelay._spawn_interactive_visible(adapter, "hello", 5)

            self.assertEqual(result["status"], "queued")
            self.assertEqual(agentrelay._gui_delivery_queue[0]["adapter_name"], "codex-interactive")
            self.assertEqual(agentrelay._gui_delivery_queue[0]["title_hint"], "codex")

        asyncio.run(run_test())

    def test_agent_launch_script_name_matches_launcher(self):
        self.assertEqual(
            agent_launch_script_name("codex-interactive"),
            "agentrelay-launch-codex-interactive.cmd",
        )

    def test_interactive_delivers_to_embedded_pty_when_running(self):
        adapter = AdapterConfig(
            name="codex-interactive",
            command=["codex"],
            mode="interactive",
        )
        session = MagicMock()
        session.alive = True
        session.grant_write.return_value = "tok"

        async def run_test():
            with patch.object(agentrelay.pty_registry, "find_alive_by_agent",
                              return_value=session):
                session.write = AsyncMock()
                result = await agentrelay._spawn_interactive_visible(
                    adapter, "hello", 1)

            self.assertEqual(result["status"], "sent")
            self.assertIn("embedded terminal", result["stdout"])
            self.assertEqual(agentrelay._gui_delivery_queue, [])
            session.write.assert_any_call("hello", "tok")
            session.write.assert_any_call("\r", "tok")

        asyncio.run(run_test())
        pty_registry._sessions.clear()


if __name__ == "__main__":
    unittest.main()
