# Client Views

## Player View (Alive)
- Role-specific information only.
- No leakage of hidden roles or inventories.
- Online status indicated (green circle).
- Player can always see own role, faction, and rank.
- Mob players can access the Mob code word via tap-to-reveal.
- Code word rotation is optional and only if Moderator enabled at game start.
- Player sees a live-player tile grid for personal bookkeeping.
- Each live-player tile includes:
- Guess dropdown with values: Police, Mob, Merchant.
- Private notes field for free text.
- Player guesses/notes are private to that player while alive.
- Notes persist for the duration of the game session.
- Players may edit or delete their own notes at any time while alive.
- Note edit history is not retained.

## Dead/Ghost View
- Can observe full player state in real time.
- Cannot participate or communicate with living players.
- Honor system: do not announce hidden info.
- Moderator may silence or disable view.
- Dead players can inspect player tiles from selected-player perspective.
- Dead players can view each selected player's guess assignments and private notes.
- Dead players have view-only notebook access (no editing).

## Jailed View
- No Dead/Ghost visibility.
- Cannot participate.
- Cannot purchase items.
- In conviction resolution, EFJ auto-use (if owned) returns the player to active state immediately.

## Moderator View
- Full visibility of all roles, inventories, and events.

## Open Discussion

- Q1: Should moderator view include per-player private notes for dispute handling, or stay excluded?
Response:
