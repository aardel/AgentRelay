import unittest

from pty_session import PTYSession, pty_registry
from ssh_hosts import SSHHost, build_ssh_shell_argv


class SSHTerminalTests(unittest.TestCase):
    def tearDown(self) -> None:
        pty_registry._sessions.clear()

    def test_build_ssh_shell_argv_uses_saved_preset(self) -> None:
        host = SSHHost(
            node_name="WINPC",
            host="192.168.1.186",
            user="aaron",
            port=2222,
            key_path="~/.ssh/id_ed25519",
        )

        argv = build_ssh_shell_argv(host, timeout=7)

        self.assertEqual(argv[0], "ssh")
        self.assertIn("-tt", argv)
        self.assertIn("BatchMode=yes", argv)
        self.assertIn("ConnectTimeout=7", argv)
        self.assertIn("-p", argv)
        self.assertIn("2222", argv)
        self.assertIn("-i", argv)
        self.assertTrue(argv[argv.index("-i") + 1].endswith(".ssh/id_ed25519"))
        self.assertEqual(argv[-1], "aaron@192.168.1.186")

    def test_ssh_sessions_do_not_count_as_active_agents(self) -> None:
        session = PTYSession(
            agent_name="ssh:WINPC",
            node="MAC",
            session_type="ssh",
            target="WINPC",
        )
        pty_registry.register(session)

        self.assertEqual(pty_registry.find_alive_by_ssh_node("WINPC"), None)
        self.assertEqual(pty_registry.list_active_agent_names(), [])
        listed = pty_registry.list()
        self.assertEqual(listed[0]["session_type"], "ssh")
        self.assertEqual(listed[0]["target"], "WINPC")


if __name__ == "__main__":
    unittest.main()
