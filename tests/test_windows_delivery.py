import asyncio
import unittest
from unittest.mock import patch

import agentrelay
from agentrelay import AdapterConfig
from agentrelay_app import agent_launch_script_name


class WindowsDeliveryTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
