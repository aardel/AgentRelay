import tempfile
import unittest
from pathlib import Path

from talk import ConversationStore, mirror_remote_turn


class TalkStoreTests(unittest.TestCase):
    def test_mirror_and_load_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConversationStore(Path(tmp))
            tid = mirror_remote_turn(
                store,
                None,
                local_node="desk",
                peer_node="bench",
                local_agent="claude",
                remote_agent="codex",
                user_message="run tests",
                assistant_reply="3 failures in auth",
            )
            messages = store.get_messages(tid)
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0].role, "user")
            self.assertEqual(messages[1].role, "assistant")
            self.assertIn("failures", messages[1].content)

    def test_format_prompt_includes_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConversationStore(Path(tmp))
            tid = mirror_remote_turn(
                store, None,
                local_node="bench", peer_node="desk",
                local_agent="codex", remote_agent="claude",
                user_message="hello", assistant_reply="hi",
            )
            prompt = store.format_prompt(
                tid, local_node="bench", from_node="desk",
                from_agent="claude", new_message="next?",
            )
            self.assertIn("hello", prompt)
            self.assertIn("next?", prompt)


if __name__ == "__main__":
    unittest.main()
