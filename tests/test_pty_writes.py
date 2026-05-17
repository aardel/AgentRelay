import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, patch

if sys.platform != "win32":
    import pty_unix
    from pty_unix import PtyUnix


@unittest.skipIf(sys.platform == "win32", "Unix PTY backend is not available")
class PtyWriteTests(unittest.TestCase):
    def test_unix_write_chunks_and_handles_partial_writes(self):
        writes = []

        def fake_write(_fd, data):
            chunk = bytes(data)
            writes.append(chunk)
            if len(chunk) > 1:
                return len(chunk) - 1
            return len(chunk)

        async def run_test():
            pty = PtyUnix()
            pty._master_fd = 123
            pty._running = True
            payload = "x" * (pty_unix.PTY_WRITE_CHUNK_BYTES + 3)
            with patch.object(pty_unix.os, "write", side_effect=fake_write):
                with patch.object(pty_unix.asyncio, "sleep", new=AsyncMock()) as sleep:
                    byte_count = await pty.write(payload)

            self.assertEqual(byte_count, len(payload.encode("utf-8")))
            self.assertGreater(len(writes), 2)
            self.assertTrue(all(len(chunk) <= pty_unix.PTY_WRITE_CHUNK_BYTES
                                for chunk in writes))
            sleep.assert_awaited()

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
