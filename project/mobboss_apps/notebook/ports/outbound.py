"""Outbound ports: external resource contracts."""

from __future__ import annotations

from typing import Protocol

from .internal import SuspectEntrySnapshot


class NotebookOutboundPort(Protocol):
    def upsert_suspect_entry(self, entry: SuspectEntrySnapshot) -> SuspectEntrySnapshot:
        ...

    def list_suspect_entries(self, game_id: str, owner_participant_id: str) -> list[SuspectEntrySnapshot]:
        ...
