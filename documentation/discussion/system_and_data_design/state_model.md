# State Model

This file describes the authoritative server state.

## Core Entities
- Player
- Role
- Inventory
- Item
- Currency balance
- Trial
- Jury
- Game room

## Player State (per player)
- id
- display_name
- role
- faction
- rank
- alive (true/false)
- jailed (true/false)
- money_balance
- inventory
- known_info (per player perspective)
- online_status
- notebook_entries (per owner):
- target_player_id
- guessed_faction (Police|Mob|Merchant)
- note_text
- updated_at
- Note rules: persists for game session only, owner may edit/delete, no edit-history retention.

TODO
- Define exact fields, types, and update rules.
- Define whether the server stores a global state and per-player views or generates views on request.

## Open Discussion

- Q1: Exact fields, types, and update rules for each entity.
Response:

- Q2: Does the server store global + per-player views or generate on request?
Response:
