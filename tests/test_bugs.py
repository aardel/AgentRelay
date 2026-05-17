"""Tests for the Bugs feature — BugStore CRUD and /api/bugs endpoints."""

import json
import tempfile
import unittest
from pathlib import Path

from bug_store import BugStore


class BugStoreTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = BugStore(path=Path(self.tmp.name) / "bugs.json")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_empty_list(self) -> None:
        self.assertEqual(self.store.list_all(), [])

    def test_create_returns_bug_with_id(self) -> None:
        bug = self.store.create("Login fails")
        self.assertIn("id", bug)
        self.assertEqual(bug["title"], "Login fails")
        self.assertEqual(bug["status"], "draft")
        self.assertEqual(bug["severity"], "medium")

    def test_list_sorted_by_severity(self) -> None:
        self.store.create("Low", severity="low")
        self.store.create("Critical", severity="critical")
        self.store.create("High", severity="high")
        severities = [b["severity"] for b in self.store.list_all()]
        self.assertEqual(severities, ["critical", "high", "low"])

    def test_update_status(self) -> None:
        bug = self.store.create("Queue me")
        updated = self.store.update(bug["id"], status="queued")
        self.assertEqual(updated["status"], "queued")  # type: ignore[index]

    def test_update_invalid_severity_ignored(self) -> None:
        bug = self.store.create("My bug", severity="medium")
        updated = self.store.update(bug["id"], severity="bogus")
        self.assertEqual(updated["severity"], "medium")  # type: ignore[index]

    def test_delete_existing(self) -> None:
        bug = self.store.create("Delete me")
        self.assertTrue(self.store.delete(bug["id"]))
        self.assertEqual(self.store.list_all(), [])


class ApiBugsTests(unittest.IsolatedAsyncioTestCase):

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
                "claude": {"command": [sys.executable, "-c", "pass"], "timeout": 5},
            },
            "rules": [],
            "default_action": "approve",
            "default_agent": "claude",
            "use_tmux": False,
            "relay": {"wait_before_send_seconds": 3},
        })
        self.relay = AgentRelay(cfg)
        self.relay.bug_store = BugStore(path=Path(self.tmp.name) / "bugs.json")
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

    async def test_create_bug(self) -> None:
        resp = await self.client.post(
            "/api/bugs",
            data=json.dumps({
                "title": "Crash on save",
                "severity": "critical",
                "steps_to_reproduce": "1. Save file",
            }),
            headers=self._headers(),
        )
        self.assertEqual(resp.status, 201)
        body = await resp.json()
        self.assertEqual(body["bug"]["title"], "Crash on save")
        self.assertEqual(body["bug"]["severity"], "critical")

    async def test_patch_bug(self) -> None:
        create = await self.client.post(
            "/api/bugs",
            data=json.dumps({"title": "To patch"}),
            headers=self._headers(),
        )
        bug_id = (await create.json())["bug"]["id"]
        resp = await self.client.patch(
            f"/api/bugs/{bug_id}",
            data=json.dumps({"status": "queued", "severity": "high"}),
            headers=self._headers(),
        )
        self.assertEqual(resp.status, 200)
        body = await resp.json()
        self.assertEqual(body["bug"]["status"], "queued")
        self.assertEqual(body["bug"]["severity"], "high")

    async def test_requires_auth(self) -> None:
        resp = await self.client.get("/api/bugs")
        self.assertEqual(resp.status, 401)


if __name__ == "__main__":
    unittest.main()
