import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

if sys.platform != "win32":
    import pty_unix
    from pty_unix import PtyUnix
else:
    import pty_windows
    from pty_windows import PtyWindows


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


@unittest.skipIf(sys.platform != "win32", "Windows PTY backend is not available")
class PtyWindowsWriteTests(unittest.TestCase):
    def test_windows_write_treats_zero_return_as_success(self):
        mock_pty = Mock(isalive=Mock(return_value=True), write=Mock(return_value=0))

        async def run_test():
            pty = PtyWindows()
            pty._pty = mock_pty
            pty._running = True
            byte_count = await pty.write("hello\r")

            self.assertEqual(byte_count, len("hello\r".encode("utf-8")))
            mock_pty.write.assert_called_once_with("hello\r")

        asyncio.run(run_test())

    def test_windows_write_serializes_concurrent_calls(self):
        order: list[str] = []

        def fake_write(text: str) -> int:
            order.append(text)
            return 0

        async def run_test():
            pty = PtyWindows()
            pty._pty = Mock(isalive=Mock(return_value=True), write=fake_write)
            pty._running = True
            await asyncio.gather(pty.write("a"), pty.write("b"))
            self.assertEqual(order, ["a", "b"])

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
