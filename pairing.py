"""Simple LAN pairing so computers can trust each other without editing files."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PairingRequest:
    id: str
    from_node: str
    from_address: str
    created: float = field(default_factory=time.time)


class PairingManager:
    def __init__(self) -> None:
        self.pending: dict[str, PairingRequest] = {}
        self._approved: dict[str, dict[str, Any]] = {}

    def request(self, from_node: str, from_address: str) -> PairingRequest:
        req = PairingRequest(
            id=secrets.token_hex(4),
            from_node=from_node,
            from_address=from_address,
        )
        self.pending[req.id] = req
        return req

    def list_pending(self) -> list[dict[str, Any]]:
        now = time.time()
        out = []
        for rid, req in list(self.pending.items()):
            if now - req.created > 300:
                del self.pending[rid]
                continue
            out.append({
                "id": req.id,
                "from_node": req.from_node,
                "from_address": req.from_address,
            })
        return out

    def approve(self, request_id: str, token: str, node_name: str) -> bool:
        req = self.pending.pop(request_id, None)
        if not req:
            return False
        self._approved[req.from_node] = {
            "token": token,
            "node_name": node_name,
            "ready": True,
        }
        return True

    def reject(self, request_id: str) -> None:
        self.pending.pop(request_id, None)

    def poll(self, from_node: str) -> dict[str, Any] | None:
        return self._approved.pop(from_node, None)
