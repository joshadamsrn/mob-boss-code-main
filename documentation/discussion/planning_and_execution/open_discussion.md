# Open Discussion

This file tracks unresolved or under-specified questions that can cause logic, flow, or implementation issues.

## High-Priority Game Logic

- Q5: Are there any circumstances where a trial can be canceled after death is confirmed (for example moderator dispute), and what happens to round flow then?
Response:

## Trials, Evidence, and Outcomes

- Q6: What determines a "correct accusation" in stash transfer rules: exact killer identity only, or attempted killer identity when vest blocked a shot?
Response:

- Q7: If multiple deaths are reported near-simultaneously before polling sync, how should the server serialize them to preserve "one murder, one trial"?
Response:

- Q8: Should jurors be excluded from voting on themselves if they are accused by edge-case timing/state bugs?
Response:

- Q9: Do moderator-initiated deaths ever create accused-selection prompts, or are they always non-trial eliminations?
Response:

## Items and Economy Integrity

- Q10: What is the authoritative item list and price table (including EFJ and vest price), and who can modify prices during a live game?
Response:

- Q12: Should the EFJ money recipient be logged for moderator only, post-game only, or never exposed beyond server audit?
Response:

- Q13: Should vest-value transfer to attacker happen at shot event time or at periodic reconciliation if report arrives late?
Response:

- Q14: What anti-leak safeguards are required to prove "money never leaves the game" (ledger reconciliation endpoint, end-of-round checksum, moderator audit screen)?
Response:

- Q15: If the destination faction has zero remaining players, where does offline liquidation value go?
Response:

## Client Views and Information Boundaries

- Q17: Should note contents be included in moderator view and audit logs for abuse/dispute handling?
Response:

- Q18: If a Mob player becomes dead/jailed, should they retain historical access to code word and Mob-only context?
Response:

## API and State Contract

- Q19: Will the server persist per-player notebook data as first-class state, and what schema/versioning should it use?
Response:

- Q20: Should clients receive deltas or full snapshots on each 5-second poll, and how is ordering guaranteed across events?
Response:

- Q21: Is polling interval globally fixed at 5 seconds, or configurable per role/environment in future without breaking fairness?
Response:

- Q22: What are the minimum required API endpoints for notebook updates, role view fetches, and mob code-word retrieval?
Response:

- Q26: Should moderator conflict handling for `report_death` remain strict-manual (refresh and retry) or add guided auto-retry/rebase UX later?
Response:
- Deferred for now. Keep strict-manual behavior with explicit 409 handling and no automatic retry.

## Operations and Dispute Handling

- Q23: What is the standard moderator SOP for disputed kill reports (deny death, defer trial, or force trial with flag)?
Response:

- Q24: What emergency-stop conditions pause the game, and how is resumed state validated to avoid duplicate transfers/votes?
Response:

- Q25: What playtest scenarios are required to validate new EFJ + vest + notebook behavior before implementation sign-off?
Response:
