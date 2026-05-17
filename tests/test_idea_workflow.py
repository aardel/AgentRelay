"""Tests for Ideas brainstorm, concept, and workflow helpers."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from idea_store import IdeaStore
from idea_workflow import brainstorm_prompt, build_concept_document, execution_prompt


class IdeaWorkflowTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = IdeaStore(path=Path(self.tmp.name) / "ideas.json")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_finding_moves_to_exploring(self) -> None:
        idea = self.store.create("Feature X")
        updated = self.store.add_finding(
            idea["id"], agent="claude", content="Looks feasible", prompt="Thoughts?",
        )
        self.assertEqual(updated["status"], "exploring")  # type: ignore[index]
        self.assertEqual(len(updated["findings"]), 1)  # type: ignore[index]

    def test_compile_concept_sets_ready(self) -> None:
        idea = self.store.create("Feature X", description="Do the thing")
        self.store.add_finding(idea["id"], agent="codex", content="Use module Y")
        updated = self.store.compile_concept(idea["id"])
        self.assertEqual(updated["status"], "ready")  # type: ignore[index]
        self.assertIn("Feature X", updated["concept"])  # type: ignore[index]

    def test_publish_concept(self) -> None:
        idea = self.store.create("Z")
        self.store.compile_concept(idea["id"])
        published = self.store.publish_concept(idea["id"])
        self.assertEqual(published["status"], "concept")  # type: ignore[index]
        self.assertIsNotNone(published["concept_published_at"])  # type: ignore[index]

    def test_brainstorm_prompt_includes_question(self) -> None:
        idea = self.store.create("Dark mode")
        p = brainstorm_prompt(idea, "How hard is this?")
        self.assertIn("Dark mode", p)
        self.assertIn("How hard is this?", p)

    def test_execution_prompt_uses_concept_when_published(self) -> None:
        idea = self.store.create("Ship it")
        self.store.update(idea["id"], concept="# Plan\nDo it", status="concept")
        self.store.publish_concept(idea["id"])
        idea = self.store.get(idea["id"])
        p = execution_prompt(idea)  # type: ignore[arg-type]
        self.assertIn("Plan", p)
        self.assertIn("execute concept", p.lower())


class ApiIdeaBrainstormTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self) -> None:
        import sys
        from aiohttp.test_utils import TestClient, TestServer
        from agentrelay import AgentRelay, Config

        self.tmp = tempfile.TemporaryDirectory()
        cfg = Config.load_dict({
            "node_name": "testnode",
            "port": 9876,
            "token": "test-token-12345678901234567890",
            "adapters": {
                "claude": {"command": [sys.executable, "-c", "print('analysis')"],
                           "timeout": 5},
            },
            "rules": [],
            "default_agent": "claude",
            "use_tmux": False,
            "relay": {"wait_before_send_seconds": 1},
        })
        self.relay = AgentRelay(cfg)
        self.relay.idea_store = IdeaStore(path=Path(self.tmp.name) / "ideas.json")
        self.app = self.relay.build_app()
        self.server = TestServer(self.app)
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        await self.client.close()
        self.tmp.cleanup()

    def _headers(self) -> dict:
        return {
            "X-Agent-Token": "test-token-12345678901234567890",
            "Content-Type": "application/json",
        }

    async def test_brainstorm_endpoint(self) -> None:
        import json

        create = await self.client.post(
            "/api/ideas",
            data=json.dumps({"title": "Brainstorm me"}),
            headers=self._headers(),
        )
        idea_id = (await create.json())["idea"]["id"]
        with patch.object(
            self.relay, "_run_idea_agent_query",
            new_callable=AsyncMock,
            return_value=("Agent says yes", {"exit_code": 0, "status": "ok"}),
        ):
            resp = await self.client.post(
                f"/api/ideas/{idea_id}/brainstorm",
                data=json.dumps({"agent": "claude", "message": "Feasible?"}),
                headers=self._headers(),
            )
        self.assertEqual(resp.status, 200)
        body = await resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["idea"]["status"], "exploring")
        self.assertEqual(len(body["idea"]["findings"]), 1)


if __name__ == "__main__":
    unittest.main()
