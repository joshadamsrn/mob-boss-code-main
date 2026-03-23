# Gameplay Sequence Diagrams

These diagrams capture the current authoritative server flow for the implemented launch handoff and confirmed-death transition.

## Room Launch Handoff

```mermaid
sequenceDiagram
    participant Mod as Moderator
    participant RoomView as rooms HTML/API edge
    participant Rooms as rooms service
    participant Gameplay as gameplay service
    participant GameRepo as gameplay repository

    Mod->>RoomView: launch room
    RoomView->>Rooms: launch_game_from_room(...)
    Rooms->>Rooms: validate room state and launch gate
    Rooms->>Gameplay: start_session_from_room(...)
    Gameplay->>GameRepo: reserve_game_id(room_id)
    Gameplay->>GameRepo: save_game_session(snapshot)
    Gameplay-->>Rooms: GameDetailsSnapshot(game_id)
    Rooms->>Rooms: mark room in_progress with returned game_id
    Rooms-->>RoomView: launch result(game_id)
    RoomView-->>Mod: redirect to /games/{game_id}/
```

## Death Report To Boundary Resolution

```mermaid
sequenceDiagram
    participant Reporter as Moderator or murdered player
    participant GameView as gameplay HTML/API edge
    participant Gameplay as gameplay service
    participant GameRepo as gameplay repository

    Reporter->>GameView: report death
    GameView->>Gameplay: report_death(...)
    Gameplay->>Gameplay: validate version and active-state invariant
    Gameplay->>Gameplay: mark murdered player dead
    Gameplay->>Gameplay: if murderer known, transfer murdered resources immediately
    Gameplay->>Gameplay: create pending_trial and accused-selection chain
    Gameplay->>GameRepo: save updated session
    GameRepo-->>Gameplay: persisted
    Gameplay-->>GameView: updated game snapshot

    alt Police chain selects accused
        GameView->>Gameplay: submit_accused_selection(...)
        Gameplay->>Gameplay: choose jury and move to trial_voting
        GameView->>Gameplay: allow_trial_voting(...)
        loop jurors vote
            GameView->>Gameplay: submit_trial_vote(...)
        end
        alt guilty and EFJ present
            Gameplay->>Gameplay: consume EFJ item
            Gameplay->>Gameplay: transfer EFJ value from central-supply ledger holder to police recipient
            Gameplay->>Gameplay: keep accused active
        else guilty and no EFJ
            Gameplay->>Gameplay: jail accused and transfer convicted resources
        else innocent
            Gameplay->>Gameplay: keep accused resources unchanged
        end
        Gameplay->>Gameplay: resolve boundary and loop or end
    else Police chain times out fully
        GameView->>Gameplay: advance_accused_selection_timeout(...)
        Gameplay->>Gameplay: resolve no_conviction and boundary checks
    end
```
