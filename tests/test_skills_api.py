"""Skills API routes."""

import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from agentrelay import AgentRelay, Config
from relay_client import SKILL_TARGETS, install_skill


def _minimal_cfg() -> Config:
    return Config.load_dict({
        "node_name": "testnode",
        "port": 9876,
        "token": "test-token-12345678901234567890",
        "adapters": {"claude": {"command": ["echo", "{prompt}"], "timeout": 5}},
        "rules": [],
        "default_action": "approve",
        "use_tmux": False,
        "relay": {"wait_before_send_seconds": 3},
    })


class SkillsApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.relay = AgentRelay(_minimal_cfg())
        self.app = self.relay.build_app()
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.headers = {"X-Agent-Token": "test-token-12345678901234567890"}

    async def asyncTearDown(self) -> None:
        await self.client.close()

    async def test_skills_list(self) -> None:
        resp = await self.client.get("/api/skills", headers=self.headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertIn("skills", data)
        self.assertTrue(any(s["name"] == "relay-send" for s in data["skills"]))

    def test_gemini_skills_install_under_skills_directory(self) -> None:
        self.assertEqual(SKILL_TARGETS["Gemini"].name, "skills")

    def test_gemini_skill_uses_yaml_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / ".gemini" / "skills"
            old = SKILL_TARGETS["Gemini"]
            SKILL_TARGETS["Gemini"] = target
            try:
                message = install_skill("relay-send", Path(td), "Gemini")
                content = (target / "relay-send" / "SKILL.md").read_text(encoding="utf-8")
            finally:
                SKILL_TARGETS["Gemini"] = old

        self.assertIn("Installed /relay-send for Gemini", message)
        self.assertTrue(content.startswith("---\n"))
        self.assertIn('name: "relay-send"', content.split("---", 2)[1])
        self.assertIn("description:", content.split("---", 2)[1])


if __name__ == "__main__":
    unittest.main()
