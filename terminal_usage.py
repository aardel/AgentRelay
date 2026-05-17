"""Token usage tracking for embedded terminal sessions.

The CLI output formats are not stable across agent versions, so the parser is
deliberately conservative: it only records values from lines that explicitly
mention token usage, remaining tokens, or context/window size.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_NUMBER_RE = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>[kKmM])?")

_USED_PATTERNS = [
    re.compile(r"(?:tokens?\s+used|used)\D{0,24}(?P<value>\d+(?:\.\d+)?\s*[kKmM]?)", re.I),
    re.compile(r"(?P<value>\d+(?:\.\d+)?\s*[kKmM]?)\s+tokens?\s+(?:used|in)", re.I),
]
_REMAINING_PATTERNS = [
    re.compile(r"(?:tokens?\s+(?:left|remaining)|remaining|left)\D{0,24}(?P<value>\d+(?:\.\d+)?\s*[kKmM]?)", re.I),
    re.compile(r"(?P<value>\d+(?:\.\d+)?\s*[kKmM]?)\s+tokens?\s+(?:left|remaining)", re.I),
]
_LIMIT_PATTERNS = [
    re.compile(r"(?:context|window)\D{0,24}(?P<value>\d+(?:\.\d+)?\s*[kKmM]?)", re.I),
    re.compile(r"(?:tokens?\s+limit|limit\D{0,12}tokens?)\D{0,24}(?P<value>\d+(?:\.\d+)?\s*[kKmM]?)", re.I),
]
_FRACTION_PATTERNS = [
    re.compile(r"(?P<used>\d+(?:\.\d+)?\s*[kKmM]?)\s*/\s*(?P<limit>\d+(?:\.\d+)?\s*[kKmM]?)\s*(?:tokens?|context|window)?", re.I),
]
_CLAUDE_USAGE_PERCENT_RE = re.compile(
    r"(?:\d+\s*-\s*hour\s+)?limit\D{0,24}(?P<percent>\d+(?:\.\d+)?)\s*%\s+used",
    re.I,
)
_RESET_RE = re.compile(r"\bresets?\s+(?:at|in)\s+(?P<value>.+)$", re.I)


def parse_token_count(value: str) -> int | None:
    """Parse token counts like "42000", "42k", or "1.2m"."""
    match = _NUMBER_RE.search(value.replace(",", ""))
    if not match:
        return None
    amount = float(match.group("num"))
    unit = (match.group("unit") or "").lower()
    if unit == "k":
        amount *= 1_000
    elif unit == "m":
        amount *= 1_000_000
    return int(amount)


def _clean_text(text: str) -> str:
    return _ANSI_RE.sub("", text).replace("\r", "\n")


@dataclass
class TerminalUsage:
    """Mutable token usage estimate for one PTY session."""

    agent_name: str
    clock: Callable[[], float] = time.time
    used: int | None = None
    remaining: int | None = None
    limit: int | None = None
    tokens_per_minute: float | None = None
    summary: str | None = None
    source: str = "none"
    updated_at: float = 0.0
    _last_used: int | None = field(default=None, init=False, repr=False)
    _last_used_at: float = field(default=0.0, init=False, repr=False)

    def observe_output(self, data: bytes) -> None:
        text = data.decode("utf-8", errors="ignore")
        if text:
            self.observe_text(text)

    def observe_text(self, text: str) -> None:
        clean = _clean_text(text)
        for line in clean.splitlines():
            self._parse_line(line)

    def snapshot(self) -> dict:
        eta_seconds = None
        if (
            self.remaining is not None
            and self.tokens_per_minute
            and self.tokens_per_minute > 0
        ):
            eta_seconds = int((self.remaining / self.tokens_per_minute) * 60)
        return {
            "agent": self.agent_name,
            "used": self.used,
            "remaining": self.remaining,
            "limit": self.limit,
            "tokens_per_minute": (
                round(self.tokens_per_minute, 1)
                if self.tokens_per_minute is not None else None
            ),
            "eta_seconds": eta_seconds,
            "summary": self.summary,
            "source": self.source,
            "updated_at": self.updated_at or None,
        }

    def _parse_line(self, line: str) -> None:
        if not line.strip():
            return
        lower = line.lower()
        changed = self._parse_usage_summary(line)
        if not any(word in lower for word in ("token", "context", "window", "limit")):
            if changed:
                self.source = "parse"
                self.updated_at = self.clock()
            return

        fraction_found = False
        for pattern in _FRACTION_PATTERNS:
            match = pattern.search(line)
            if match:
                changed |= self._set_used(parse_token_count(match.group("used")))
                changed |= self._set_limit(parse_token_count(match.group("limit")))
                fraction_found = True
                break
        for pattern in _USED_PATTERNS:
            match = pattern.search(line)
            if match:
                changed |= self._set_used(parse_token_count(match.group("value")))
                break
        for pattern in _REMAINING_PATTERNS:
            match = pattern.search(line)
            if match:
                changed |= self._set_remaining(parse_token_count(match.group("value")))
                break
        if not fraction_found:
            for pattern in _LIMIT_PATTERNS:
                match = pattern.search(line)
                if match:
                    changed |= self._set_limit(parse_token_count(match.group("value")))
                    break

        if self.limit is not None and self.used is not None and self.remaining is None:
            if self.limit >= self.used:
                self.remaining = self.limit - self.used
                changed = True
        if changed:
            self.source = "parse"
            self.updated_at = self.clock()

    def _parse_usage_summary(self, line: str) -> bool:
        percent_match = _CLAUDE_USAGE_PERCENT_RE.search(line)
        if percent_match:
            percent = percent_match.group("percent")
            next_summary = f"Claude usage: {percent}% used"
            if self.summary != next_summary:
                self.summary = next_summary
                return True
            return False

        reset_match = _RESET_RE.search(line.strip())
        if reset_match and self.summary:
            reset = reset_match.group("value").strip()
            next_summary = f"{self.summary} | Resets at {reset}"
            if self.summary != next_summary:
                self.summary = next_summary
                return True
        return False

    def _set_used(self, value: int | None) -> bool:
        if value is None:
            return False
        now = self.clock()
        if self._last_used is not None and value > self._last_used and now > self._last_used_at:
            sample = (value - self._last_used) / ((now - self._last_used_at) / 60)
            self.tokens_per_minute = (
                sample if self.tokens_per_minute is None
                else (self.tokens_per_minute * 0.7) + (sample * 0.3)
            )
        self._last_used = value
        self._last_used_at = now
        if self.used == value:
            return False
        self.used = value
        if self.limit is not None and self.limit >= value:
            self.remaining = self.limit - value
        return True

    def _set_remaining(self, value: int | None) -> bool:
        if value is None or self.remaining == value:
            return False
        self.remaining = value
        if self.used is not None:
            self.limit = self.used + value
        return True

    def _set_limit(self, value: int | None) -> bool:
        if value is None or self.limit == value:
            return False
        self.limit = value
        if self.used is not None and value >= self.used:
            self.remaining = value - self.used
        return True
