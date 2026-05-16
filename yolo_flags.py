"""
YOLO / skip-permissions flags for interactive agent PTY launches.

See docs/ai-cli-agents-yolo-flags.md for full reference.
"""

from __future__ import annotations

# agent family -> argv flags inserted after the binary (position 1)
YOLO_FLAGS: dict[str, list[str]] = {
    "claude": ["--dangerously-skip-permissions"],
    "codex": ["--dangerously-bypass-approvals-and-sandbox"],
    "gemini": ["-y"],
    "copilot": ["--allow-all"],
    "cursor": ["--yolo", "--force"],
    "aider": ["--yes-always"],
}

def detect_agent_family(adapter_id: str, argv: list[str]) -> str | None:
    """Guess agent family from adapter id and launch argv."""
    hay = " ".join([adapter_id, *argv]).lower()
    for name in ("claude", "codex", "gemini", "copilot", "cursor", "aider"):
        if name in hay:
            return name
    return None


def apply_yolo_flags(argv: list[str], adapter_id: str, yolo: bool) -> list[str]:
    """Return argv with YOLO flags inserted after the executable when enabled."""
    if not yolo or not argv:
        return argv
    family = detect_agent_family(adapter_id, argv)
    if not family:
        return argv
    flags = YOLO_FLAGS.get(family, [])
    if not flags:
        return argv
    out = [argv[0]]
    for flag in flags:
        if flag not in argv:
            out.append(flag)
    for part in argv[1:]:
        if part not in out:
            out.append(part)
    return out


def yolo_supported(adapter_id: str, argv: list[str]) -> bool:
    family = detect_agent_family(adapter_id, argv)
    return bool(family and family in YOLO_FLAGS)
