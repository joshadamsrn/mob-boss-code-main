# feature_trials_and_convictions

## Goal
Define trial trigger, accused selection, jury voting, conviction outcomes, and transfer routing.

## Rules
- Trial triggers only on confirmed death (not vest-blocked shot).
- Public trial announcement occurs only after an accused is selected.
- Jury size is odd, minimum 3, and selected from living non-jailed players.
- Voting outcomes:
- Guilty + EFJ owned: EFJ auto-uses; accused remains active; no transfer/reveal.
- Guilty + no EFJ: accused eliminated.
- Innocent: accused keeps resources; game advances.
- Correct accusation means conviction of actual murderer.
- Correct accusation + guilty + no EFJ: Police Chief receives accused resources.
- Wrong accusation + guilty + no EFJ: Mob Boss receives accused resources.

## Invariants
- Trial flow is server-authoritative.
- Moderator does not resolve conviction correctness.

## Open Items
- Trial cancellation policy for moderator dispute after death confirmation.
