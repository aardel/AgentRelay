import tempfile
import unittest
from pathlib import Path

from agent_data import AgentDataStore


class AgentDataStoreTests(unittest.TestCase):
    def test_resume_agent_id_cannot_traverse_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = AgentDataStore(root)

            store.save_resume("../outside", "safe")

            self.assertFalse((root.parent / "outside.md").exists())
            self.assertEqual(store.get_resume("../outside"), "safe")
            self.assertIn("../outside", store.list_resumes())

    def test_memory_must_be_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AgentDataStore(Path(tmp))

            with self.assertRaises(ValueError):
                store.save_memory("agent", ["not", "an", "object"])  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
