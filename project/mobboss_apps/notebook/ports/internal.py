"""Internal ports: DTOs and data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FactionGuess = Literal["Police", "Mob", "Merchant"]


@dataclass(frozen=True)
class UpsertSuspectEntryCommand:
    game_id: str
    owner_participant_id: str
    target_participant_id: str
    presumed_faction: FactionGuess
    presumed_role: str
    confidence: int
    note_text: str

    @classmethod
    def from_json(cls, payload: dict) -> "UpsertSuspectEntryCommand":
        return cls(
            game_id=str(payload["game_id"]).strip(),
            owner_participant_id=str(payload["owner_participant_id"]).strip(),
            target_participant_id=str(payload["target_participant_id"]).strip(),
            presumed_faction=payload["presumed_faction"],
            presumed_role=str(payload.get("presumed_role", "")).strip(),
            confidence=int(payload.get("confidence", 0)),
            note_text=str(payload.get("note_text", "")).strip(),
        )


@dataclass(frozen=True)
class SuspectEntrySnapshot:
    game_id: str
    owner_participant_id: str
    target_participant_id: str
    presumed_faction: FactionGuess
    presumed_role: str
    confidence: int
    note_text: str
    updated_at_iso: str
