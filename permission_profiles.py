"""Permission profiles for agent launches.

Three levels of trust, each mapping to per-agent CLI flags:

  safe          — default confirmation behavior, no extra flags
  project_write — auto-approve file reads/edits, shell commands still prompt
  full_auto     — no confirmation prompts (mirrors YOLO_FLAGS)

Use apply_profile_flags() to build argv for a launch.
"""

from __future__ import annotations

from yolo_flags import YOLO_FLAGS, detect_agent_family

# Flags added for the project_write tier.
# Only agents with a real CLI middle-ground get an entry here.
# Agents without one (claude, gemini, cursor, aider) run at safe behavior;
# see PROFILE_NOTES for the settings-file alternative.
_PROJECT_WRITE_FLAGS: dict[str, list[str]] = {
    "codex":   ["--full-auto"],          # keeps sandbox, auto-approves file ops
    "copilot": ["--allow-all-paths"],    # skip path prompts, keep URL/command approval
}

# Human-readable hints for agents with no project_write CLI flag.
_PROJECT_WRITE_NOTES: dict[str, str] = {
    "claude":  "Use .claude/settings.json allowedTools for granular tool control.",
    "gemini":  "No CLI flag available; configure via ~/.gemini/settings.json.",
    "cursor":  "Use cursor-agent sandbox.json for per-tool restrictions.",
    "aider":   "No middle-ground flag; use --yes-always (full_auto) or no flag (safe).",
}

PROFILES: dict[str, dict] = {
    "safe": {
        "label":       "Safe",
        "description": "Default — agent asks before file edits, shell commands, and risky actions.",
        "warning":     False,
        "flags":       {},
        "notes":       {},
    },
    "project_write": {
        "label":       "Project Write",
        "description": "Auto-approve file reads and edits; shell commands still require approval.",
        "warning":     False,
        "flags":       _PROJECT_WRITE_FLAGS,
        "notes":       _PROJECT_WRITE_NOTES,
    },
    "full_auto": {
        "label":       "Full Auto",
        "description": "No confirmation prompts. Agent operates without asking. Trusted projects only.",
        "warning":     True,
        "flags":       YOLO_FLAGS,
        "notes":       {},
    },
}

DEFAULT_PROFILE = "safe"
VALID_PROFILES = frozenset(PROFILES)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def apply_profile_flags(argv: list[str], adapter_id: str, profile: str) -> list[str]:
    """Return argv with the appropriate flags for *profile* inserted after argv[0].

    Falls through to the safe (no-op) path for unknown profiles or agents
    without flags at the requested level.
    """
    if not argv:
        return argv
    profile_def = PROFILES.get(profile or DEFAULT_PROFILE, PROFILES[DEFAULT_PROFILE])
    family = detect_agent_family(adapter_id, argv)
    if not family:
        return argv
    flags = profile_def["flags"].get(family, [])
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


def profile_for_yolo(yolo: bool) -> str:
    """Map the legacy boolean yolo flag to a profile name."""
    return "full_auto" if yolo else DEFAULT_PROFILE


def is_elevated(profile: str) -> bool:
    """True when the profile bypasses normal confirmation prompts."""
    return profile == "full_auto"


def profile_label(profile: str) -> str:
    return PROFILES.get(profile, {}).get("label", profile or DEFAULT_PROFILE)


def profile_note(profile: str, agent_family: str) -> str | None:
    """Return a human-readable note for agents without a flag at this profile level."""
    return PROFILES.get(profile, {}).get("notes", {}).get(agent_family)


def profile_summary() -> list[dict]:
    """Return a list of profile dicts suitable for the GUI's /api/profiles endpoint."""
    return [
        {
            "id":          pid,
            "label":       p["label"],
            "description": p["description"],
            "warning":     p["warning"],
            "agents":      {
                fam: {
                    "flags": p["flags"].get(fam, []),
                    "note":  p["notes"].get(fam),
                }
                for fam in sorted(set(list(p["flags"]) + list(p["notes"])) | set(YOLO_FLAGS))
            },
        }
        for pid, p in PROFILES.items()
    ]
