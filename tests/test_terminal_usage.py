import unittest

from terminal_usage import TerminalUsage, parse_token_count


class TerminalUsageTests(unittest.TestCase):
    def test_parse_token_count_units(self) -> None:
        self.assertEqual(parse_token_count("42k"), 42000)
        self.assertEqual(parse_token_count("1.5m"), 1500000)
        self.assertEqual(parse_token_count("12,345"), 12345)

    def test_observe_fraction_sets_used_limit_remaining(self) -> None:
        usage = TerminalUsage("codex")

        usage.observe_text("context 42k / 200k tokens")

        data = usage.snapshot()
        self.assertEqual(data["used"], 42000)
        self.assertEqual(data["limit"], 200000)
        self.assertEqual(data["remaining"], 158000)
        self.assertEqual(data["source"], "parse")

    def test_observe_updates_tokens_per_minute(self) -> None:
        now = 1000.0

        def clock() -> float:
            return now

        usage = TerminalUsage("claude", clock=clock)
        usage.observe_text("tokens used: 1000")
        now = 1060.0
        usage.observe_text("tokens used: 1600")

        data = usage.snapshot()
        self.assertEqual(data["used"], 1600)
        self.assertEqual(data["tokens_per_minute"], 600.0)


if __name__ == "__main__":
    unittest.main()
