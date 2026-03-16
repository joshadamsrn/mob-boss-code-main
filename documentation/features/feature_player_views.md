# feature_player_views

## Goal
Define visibility boundaries for alive, dead, jailed, moderator, and role-specific data.

## Rules
- Alive player can view own role/faction/rank.
- Mob code word is tap-to-reveal.
- Optional code-word rotation is a moderator pre-game setting.
- Alive notebook supports per-player faction guess (Police/Mob/Merchant) and private notes.
- Notes persist for session duration.
- Note owner may edit/delete notes while alive.
- Note edit history is not retained.
- Dead players can inspect selected-player notebook data in view-only mode.

## Invariants
- Perspective filtering prevents hidden-role leakage.
- Dead players cannot take game actions.

## Open Items
- Whether moderator can read player private notes.
