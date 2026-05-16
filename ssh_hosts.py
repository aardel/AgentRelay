"""SSH host preset storage and management.

Presets are stored in ~/.config/agentrelay/ssh_hosts.json (chmod 600).
Key-based auth only — no passphrase storage. Connectivity tested on save.

Schema (one entry per node_name):
  {
    "node_name": "MACMINI",
    "host": "192.168.1.50",
    "port": 22,
    "user": "alice",
    "key_path": "~/.ssh/id_ed25519",
    "machine_id": "abc-def-...",
    "added_at": 1716000000.0,
    "last_ok": 1716001000.0
  }
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "agentrelay"
SSH_HOSTS_FILE = CONFIG_DIR / "ssh_hosts.json"


# ---------------------------------------------------------------------------
# machine_id helpers
# ---------------------------------------------------------------------------

def get_machine_id() -> str:
    """Return a stable per-machine UUID string (best-effort, never raises)."""
    sys = platform.system()
    try:
        if sys == "Linux":
            p = Path("/etc/machine-id")
            if p.exists():
                return p.read_text().strip()
        elif sys == "Darwin":
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                text=True, timeout=5,
            )
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2]
        elif sys == "Windows":
            out = subprocess.check_output(
                ["wmic", "csproduct", "get", "UUID"],
                text=True, timeout=5,
            )
            lines = [l.strip() for l in out.splitlines() if l.strip()]
            if len(lines) >= 2:
                return lines[1]
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SSHHost:
    node_name: str
    host: str
    user: str
    port: int = 22
    key_path: str = ""
    machine_id: str = ""
    added_at: float = field(default_factory=time.time)
    last_ok: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SSHHost":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class SSHHostStore:
    """Read/write ssh_hosts.json with atomic saves."""

    def __init__(self, path: Path = SSH_HOSTS_FILE) -> None:
        self._path = path

    # -- internal --

    def _load_raw(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text())
            if isinstance(data, list):
                return data
        except Exception:
            pass
        return []

    def _save_raw(self, records: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(records, indent=2))
        tmp.replace(self._path)
        try:
            os.chmod(self._path, 0o600)
        except Exception:
            pass

    # -- public --

    def list(self) -> list[SSHHost]:
        return [SSHHost.from_dict(r) for r in self._load_raw()]

    def get(self, node_name: str) -> SSHHost | None:
        for r in self._load_raw():
            if r.get("node_name") == node_name:
                return SSHHost.from_dict(r)
        return None

    def get_by_machine_id(self, machine_id: str) -> SSHHost | None:
        if not machine_id:
            return None
        for r in self._load_raw():
            if r.get("machine_id") == machine_id:
                return SSHHost.from_dict(r)
        return None

    def save(self, host: SSHHost) -> None:
        records = self._load_raw()
        for i, r in enumerate(records):
            if r.get("node_name") == host.node_name:
                records[i] = host.to_dict()
                self._save_raw(records)
                return
        records.append(host.to_dict())
        self._save_raw(records)

    def update_last_ok(self, node_name: str) -> None:
        records = self._load_raw()
        for r in records:
            if r.get("node_name") == node_name:
                r["last_ok"] = time.time()
                self._save_raw(records)
                return

    def delete(self, node_name: str) -> bool:
        records = self._load_raw()
        new = [r for r in records if r.get("node_name") != node_name]
        if len(new) == len(records):
            return False
        self._save_raw(new)
        return True

    def rename_node(self, old_name: str, new_name: str) -> bool:
        """Update node_name in an existing preset (drift detection rename)."""
        records = self._load_raw()
        for r in records:
            if r.get("node_name") == old_name:
                r["node_name"] = new_name
                self._save_raw(records)
                return True
        return False

    def has_preset(self, node_name: str) -> bool:
        return self.get(node_name) is not None


# ---------------------------------------------------------------------------
# Connectivity test
# ---------------------------------------------------------------------------

def test_ssh_connectivity(
    host: str,
    user: str,
    port: int = 22,
    key_path: str = "",
    timeout: int = 5,
) -> tuple[bool, str]:
    """Run `ssh -o BatchMode=yes user@host echo ok` and return (ok, message)."""
    if not shutil.which("ssh"):
        return False, "ssh not found on PATH"

    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={timeout}",
        "-o", "StrictHostKeyChecking=accept-new",
        "-p", str(port),
    ]
    if key_path:
        expanded = str(Path(key_path).expanduser())
        cmd += ["-i", expanded]
    cmd += [f"{user}@{host}", "echo ok"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
        if result.returncode == 0 and "ok" in result.stdout:
            return True, "connected"
        stderr = result.stderr.strip()
        return False, stderr or f"exit code {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store: SSHHostStore | None = None


def get_store() -> SSHHostStore:
    global _store
    if _store is None:
        _store = SSHHostStore()
    return _store
