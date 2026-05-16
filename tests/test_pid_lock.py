import tempfile
import unittest
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import agentrelay


class PidLockTests(unittest.TestCase):
    def test_pid_lock_uses_existing_temp_directory(self):
        path = agentrelay.pid_file_path()

        self.assertEqual(path, Path(tempfile.gettempdir()) / "agentrelay.pid")
        self.assertTrue(path.parent.exists())

    def test_current_process_pid_is_running(self):
        self.assertTrue(agentrelay.pid_is_running(os.getpid()))

    def test_pid_lock_refuses_live_existing_pid(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "agentrelay.pid"
            path.write_text(str(os.getpid()))

            self.assertFalse(agentrelay.acquire_pid_lock(path))

    def test_pid_lock_replaces_stale_pid_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "agentrelay.pid"
            path.write_text("999999999")

            self.assertTrue(agentrelay.acquire_pid_lock(path))
            self.assertEqual(path.read_text(), str(os.getpid()))


if __name__ == "__main__":
    unittest.main()
