"""Inbound ports: system stimulation contracts."""

from __future__ import annotations

from typing import Protocol

from .internal import SuspectEntrySnapshot, UpsertSuspectEntryCommand


class NotebookInboundPort(Protocol):
    def upsert_suspect_entry(self, command: UpsertSuspectEntryCommand) -> SuspectEntrySnapshot:
        """One record per (owner_participant_id, target_participant_id)."""
        ...

    def list_suspect_entries(self, game_id: str, owner_participant_id: str) -> list[SuspectEntrySnapshot]:
        ...
