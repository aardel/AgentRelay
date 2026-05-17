"""Tests for the Ideas feature — IdeaStore CRUD and /api/ideas endpoints."""

import json
import tempfile
import unittest
from pathlib import Path

from idea_store import IdeaStore


# ---------------------------------------------------------------------------
# IdeaStore unit tests
# ---------------------------------------------------------------------------

class IdeaStoreTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = IdeaStore(path=Path(self.tmp.name) / "ideas.json")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_empty_list(self) -> None:
        self.assertEqual(self.store.list_all(), [])

    def test_create_returns_idea_with_id(self) -> None:
        idea = self.store.create("Test idea")
        self.assertIn("id", idea)
        self.assertEqual(idea["title"], "Test idea")
        self.assertEqual(idea["status"], "draft")
        self.assertEqual(idea["priority"], "medium")

    def test_create_persists(self) -> None:
        self.store.create("Persist me")
        store2 = IdeaStore(path=self.store._path)
        self.assertEqual(len(store2.list_all()), 1)

    def test_list_sorted_by_priority(self) -> None:
        self.store.create("Low priority", priority="low")
        self.store.create("High priority", priority="high")
        self.store.create("Medium priority", priority="medium")
        ids = [i["priority"] for i in self.store.list_all()]
        self.assertEqual(ids, ["high", "medium", "low"])

    def test_get_existing(self) -> None:
        created = self.store.create("Get me")
        found = self.store.get(created["id"])
        self.assertIsNotNone(found)
        self.assertEqual(found["title"], "Get me")  # type: ignore[index]

    def test_get_missing_returns_none(self) -> None:
        self.assertIsNone(self.store.get("nonexistent"))

    def test_update_title_and_priority(self) -> None:
        idea = self.store.create("Old title", priority="low")
        updated = self.store.update(idea["id"], title="New title", priority="high")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["title"], "New title")  # type: ignore[index]
        self.assertEqual(updated["priority"], "high")  # type: ignore[index]

    def test_update_status(self) -> None:
        idea = self.store.create("Queue me")
        updated = self.store.update(idea["id"], status="queued")
        self.assertEqual(updated["status"], "queued")  # type: ignore[index]

    def test_update_invalid_priority_ignored(self) -> None:
        idea = self.store.create("My idea", priority="medium")
        updated = self.store.update(idea["id"], priority="bogus")
        self.assertEqual(updated["priority"], "medium")  # type: ignore[index]

    def test_update_invalid_status_ignored(self) -> None:
        idea = self.store.create("My idea")
        updated = self.store.update(idea["id"], status="flying")
        self.assertEqual(updated["status"], "draft")  # type: ignore[index]

    def test_update_missing_returns_none(self) -> None:
        self.assertIsNone(self.store.update("bad-id", title="x"))

    def test_delete_existing(self) -> None:
        idea = self.store.create("Delete me")
        self.assertTrue(self.store.delete(idea["id"]))
        self.assertEqual(self.store.list_all(), [])

    def test_delete_missing_returns_false(self) -> None:
        self.assertFalse(self.store.delete("nonexistent"))

    def test_unknown_field_not_stored(self) -> None:
        idea = self.store.create("Idea")
        updated = self.store.update(idea["id"], evil_field="injected")
        self.assertNotIn("evil_field", updated)  # type: ignore[operator]


# ---------------------------------------------------------------------------
# /api/ideas HTTP endpoint tests
# ---------------------------------------------------------------------------

class ApiIdeasTests(unittest.IsolatedAsyncioTestCase):

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
            "use_tmux": False,
            "relay": {"wait_before_send_seconds": 3},
        })
        self.relay = AgentRelay(cfg)
        self.relay.idea_store = IdeaStore(
            path=Path(self.tmp.name) / "ideas.json"
        )
        self.app = self.relay.build_app()
        self.server = TestServer(self.app)
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        await self.client.close()
        self.tmp.cleanup()

    def _headers(self) -> dict:
        return {"X-Agent-Token": "test-token-12345678901234567890",
                "Content-Type": "application/json"}

    async def test_list_empty(self) -> None:
        resp = await self.client.get("/api/ideas", headers=self._headers())
        self.assertEqual(resp.status, 200)
        body = await resp.json()
        self.assertEqual(body["ideas"], [])

    async def test_create_idea(self) -> None:
        resp = await self.client.post(
            "/api/ideas",
            data=json.dumps({"title": "My idea", "priority": "high"}),
            headers=self._headers(),
        )
        self.assertEqual(resp.status, 201)
        body = await resp.json()
        self.assertEqual(body["idea"]["title"], "My idea")
        self.assertEqual(body["idea"]["priority"], "high")
        self.assertEqual(body["idea"]["status"], "draft")

    async def test_create_requires_title(self) -> None:
        resp = await self.client.post(
            "/api/ideas",
            data=json.dumps({"description": "no title"}),
            headers=self._headers(),
        )
        self.assertEqual(resp.status, 400)

    async def test_list_returns_created_idea(self) -> None:
        await self.client.post(
            "/api/ideas",
            data=json.dumps({"title": "Listed idea"}),
            headers=self._headers(),
        )
        resp = await self.client.get("/api/ideas", headers=self._headers())
        body = await resp.json()
        self.assertEqual(len(body["ideas"]), 1)
        self.assertEqual(body["ideas"][0]["title"], "Listed idea")

    async def test_patch_idea(self) -> None:
        create = await self.client.post(
            "/api/ideas",
            data=json.dumps({"title": "To patch"}),
            headers=self._headers(),
        )
        idea_id = (await create.json())["idea"]["id"]
        resp = await self.client.patch(
            f"/api/ideas/{idea_id}",
            data=json.dumps({"status": "queued", "priority": "high"}),
            headers=self._headers(),
        )
        self.assertEqual(resp.status, 200)
        body = await resp.json()
        self.assertEqual(body["idea"]["status"], "queued")
        self.assertEqual(body["idea"]["priority"], "high")

    async def test_patch_missing_returns_404(self) -> None:
        resp = await self.client.patch(
            "/api/ideas/doesnotexist",
            data=json.dumps({"title": "x"}),
            headers=self._headers(),
        )
        self.assertEqual(resp.status, 404)

    async def test_delete_idea(self) -> None:
        create = await self.client.post(
            "/api/ideas",
            data=json.dumps({"title": "To delete"}),
            headers=self._headers(),
        )
        idea_id = (await create.json())["idea"]["id"]
        resp = await self.client.delete(
            f"/api/ideas/{idea_id}", headers=self._headers()
        )
        self.assertEqual(resp.status, 200)
        body = await resp.json()
        self.assertTrue(body["ok"])

        list_resp = await self.client.get("/api/ideas", headers=self._headers())
        self.assertEqual((await list_resp.json())["ideas"], [])

    async def test_delete_missing_returns_404(self) -> None:
        resp = await self.client.delete(
            "/api/ideas/doesnotexist", headers=self._headers()
        )
        self.assertEqual(resp.status, 404)

    async def test_requires_auth(self) -> None:
        resp = await self.client.get("/api/ideas")
        self.assertEqual(resp.status, 401)


if __name__ == "__main__":
    unittest.main()
