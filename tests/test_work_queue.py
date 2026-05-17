"""Tests for ideas/bugs work queue auto-run."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bug_store import BugStore
from idea_store import IdeaStore
from work_queue_runner import (
    _queued_items,
    build_work_prompt,
    try_dispatch_next,
)


class WorkQueueRunnerTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.idea_store = IdeaStore(path=Path(self.tmp.name) / "ideas.json")
        self.bug_store = BugStore(path=Path(self.tmp.name) / "bugs.json")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_queued_items_critical_bug_before_low_idea(self) -> None:
        self.idea_store.create("Low idea", priority="low")
        self.idea_store.update(
            self.idea_store.list_all()[0]["id"], status="queued",
        )
        bug = self.bug_store.create("Critical bug", severity="critical")
        self.bug_store.update(bug["id"], status="queued")
        items = _queued_items(self.idea_store, self.bug_store)
        self.assertEqual(items[0][0], "bug")
        self.assertEqual(items[0][1]["severity"], "critical")

    def test_build_bug_prompt_includes_steps(self) -> None:
        bug = self.bug_store.create(
            "Save crash",
            description="App exits",
            severity="high",
            steps_to_reproduce="Click save",
        )
        prompt = build_work_prompt("bug", bug)
        self.assertIn("Save crash", prompt)
        self.assertIn("Click save", prompt)
        self.assertIn("fix this bug", prompt)

    def test_build_idea_prompt(self) -> None:
        idea = self.idea_store.create("Dark mode", description="Add theme toggle")
        prompt = build_work_prompt("idea", idea)
        self.assertIn("Dark mode", prompt)
        self.assertIn("implement", prompt.lower())


class WorkQueueDispatchTests(unittest.IsolatedAsyncioTestCase):

    async def test_idle_false_when_agents_active(self) -> None:
        import sys
        from agentrelay import AgentRelay, Config

        cfg = Config.load_dict({
            "node_name": "testnode",
            "port": 9876,
            "token": "test-token-12345678901234567890",
            "adapters": {
                "claude": {"command": [sys.executable, "-c", "pass"], "timeout": 5},
            },
            "rules": [],
            "default_agent": "claude",
            "use_tmux": False,
            "relay": {"wait_before_send_seconds": 1},
        })
        relay = AgentRelay(cfg)
        with patch("agentrelay.list_active_agent_names", return_value=["claude"]):
            result = await try_dispatch_next(relay)
        self.assertFalse(result["idle"])
        self.assertFalse(result["dispatched"])

    async def test_dispatches_when_idle(self) -> None:
        import sys
        from agentrelay import AgentRelay, Config

        tmp = tempfile.TemporaryDirectory()
        cfg = Config.load_dict({
            "node_name": "testnode",
            "port": 9876,
            "token": "test-token-12345678901234567890",
            "adapters": {
                "claude": {"command": [sys.executable, "-c", "pass"], "timeout": 5},
            },
            "rules": [],
            "default_agent": "claude",
            "use_tmux": False,
            "relay": {"wait_before_send_seconds": 1},
        })
        relay = AgentRelay(cfg)
        relay.idea_store = IdeaStore(path=Path(tmp.name) / "ideas.json")
        idea = relay.idea_store.create("Auto idea")
        relay.idea_store.update(idea["id"], status="queued")

        with patch("agentrelay.list_active_agent_names", return_value=[]):
            with patch(
                "agentrelay._deliver_prompt_to_pty",
                new_callable=AsyncMock,
                return_value=False,
            ):
                result = await try_dispatch_next(relay)

        self.assertTrue(result["dispatched"])
        self.assertEqual(result["kind"], "idea")
        self.assertTrue(result.get("needs_terminal"))
        updated = relay.idea_store.get(idea["id"])
        self.assertEqual(updated["status"], "in_progress")  # type: ignore[index]
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
