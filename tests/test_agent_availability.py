import sys
import unittest
from unittest.mock import patch

from agentrelay import AdapterConfig, Config
from relay_client import (
    available_agent_labels,
    is_adapter_available,
    unavailable_agent_labels,
)


class AgentAvailabilityTests(unittest.TestCase):
    def _cfg(self) -> Config:
        return Config.load_dict({
            "node_name": "test",
            "port": 9876,
            "token": "t" * 32,
            "adapters": {
                "claude": {"command": [sys.executable, "-c", "pass"]},
                "gemini-interactive": {
                    "command": ["gemini"],
                    "mode": "interactive",
                },
            },
            "rules": [],
            "default_action": "approve",
        })

    def test_is_adapter_available_uses_path_lookup(self) -> None:
        adapter = AdapterConfig(name="gemini-interactive", command=["gemini"], mode="interactive")
        with patch("shutil.which", return_value=None):
            self.assertFalse(is_adapter_available("gemini-interactive", adapter))
        with patch("shutil.which", return_value="/usr/bin/gemini"):
            self.assertTrue(is_adapter_available("gemini-interactive", adapter))

    def test_available_agent_labels_filters_missing(self) -> None:
        cfg = self._cfg()

        def fake_which(exe: str):
            return sys.executable if exe == sys.executable else None

        with patch("shutil.which", side_effect=fake_which):
            available = available_agent_labels(cfg)
            missing = unavailable_agent_labels(cfg)

        self.assertEqual([a["id"] for a in available], ["claude"])
        self.assertEqual([a["id"] for a in missing], ["gemini-interactive"])
        self.assertIn("not found on PATH", missing[0]["reason"])


if __name__ == "__main__":
    unittest.main()
