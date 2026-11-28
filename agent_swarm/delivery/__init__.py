"""Delivery backends: what carries a message from the hub to an agent."""

from __future__ import annotations

import os
from pathlib import Path

from .base import (
    Capabilities,
    DeliveryBackend,
    Inbound,
    Node,
    NodeRegistry,
    PaneSnapshot,
    Resolved,
    Result,
    Spawned,
    Unavailable,
    Unsupported,
    new_op_id,
    unsupported,
)

BACKENDS = ("tmux", "rhizome")


def create(name: str | None = None, *, attachments_root: Path, data_dir: Path) -> DeliveryBackend:
    """The backend named by `name`, else by BUZZ_DELIVERY, else tmux."""
    name = (name or os.environ.get("BUZZ_DELIVERY") or "tmux").strip().lower()
    if name == "tmux":
        from .tmux_backend import TmuxBackend

        return TmuxBackend(attachments_root)
    if name == "rhizome":
        from .rhizome_backend import RhizomeBackend

        return RhizomeBackend.from_env(attachments_root=attachments_root, data_dir=data_dir)
    raise ValueError(f"unknown delivery backend {name!r}; BUZZ_DELIVERY must be one of {', '.join(BACKENDS)}")


__all__ = [
    "BACKENDS", "Capabilities", "DeliveryBackend", "Inbound", "Node", "NodeRegistry",
    "PaneSnapshot", "Resolved", "Result", "Spawned", "Unavailable", "Unsupported",
    "create", "new_op_id", "unsupported",
]
