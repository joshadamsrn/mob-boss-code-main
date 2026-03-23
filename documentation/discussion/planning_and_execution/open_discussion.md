# Open Discussion

This file tracks unresolved or under-specified questions that can cause logic, flow, or implementation issues.

## High-Priority Game Logic

- Q5: Are there any circumstances where a trial can be canceled after death is confirmed (for example moderator dispute), and what happens to round flow then?
Response:

## Trials, Evidence, and Outcomes

- Q6: What determines a "correct accusation" in stash transfer rules: exact killer identity only, or attempted killer identity when vest blocked a shot?
Response:
- Exact killer identity only.
- Vest-blocked shots do not enter trial flow, so they do not participate in conviction-correctness evaluation.

- Q7: If multiple deaths are reported near-simultaneously before polling sync, how should the server serialize them to preserve "one murder, one trial"?
Response:

- Q8: Should jurors be excluded from voting on themselves if they are accused by edge-case timing/state bugs?
Response:

- Q9: Do moderator-initiated deaths ever create accused-selection prompts, or are they always non-trial eliminations?
Response:

## Items and Economy Integrity

- Q10: What is the authoritative item list and price table (including EFJ and vest price), and who can modify prices during a live game?
Response:
- The authoritative item list is the room/game catalog seeded from economy defaults and carried into the launched gameplay session.
- Baseline prices remain moderator-controlled per the room preparation and economy feature specs.
- Current default specialty-item prices remain percentage-derived at room setup time unless moderator-adjusted.

- Q12: Should the EFJ money recipient be logged for moderator only, post-game only, or never exposed beyond server audit?
Response:
- Keep the recipient private to the recipient plus server-side audit data.
- Do not expose the EFJ bribe recipient in public or general player views.

- Q13: Should vest-value transfer to attacker happen at shot event time or at periodic reconciliation if report arrives late?
Response:
- At resolved vest-trigger event time.
- Do not defer vest-value routing to periodic reconciliation.

- Q14: What anti-leak safeguards are required to prove "money never leaves the game" (ledger reconciliation endpoint, end-of-round checksum, moderator audit screen)?
Response:
- Strict ledger reconciliation on gameplay session save for implemented transfer routes.
- Persisted ledger checksum on session snapshots.
- Keep any future moderator audit surface role-safe and separate from public/player views.

- Q15: If the destination faction has zero remaining players, where does offline liquidation value go?
Response:

## Client Views and Information Boundaries

- Q17: Should note contents be included in moderator view and audit logs for abuse/dispute handling?
Response:

- Q18: If a Mob player becomes dead/jailed, should they retain historical access to code word and Mob-only context?
Response:

- Q27: Do the remaining placeholder role cards imply missing activated powers that should be implemented now?
Response:
- No.
- Current authoritative rules support only these live player-triggered role powers:
  - `Don`
  - `Under Boss`
  - `Kingpin`
- Current authoritative rules support these automatic-only role effects:
  - `Chief of Police`
  - `Mob Boss`
  - `Knife Hobo`
- Remaining named Police, Mob-operative, and trade titles are treated as passive-only summary roles in the current implementation phase.
- Any future activated power for those titles requires an explicit rules/spec update before code work begins.

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
- EFJ: guilty verdict with EFJ owned, EFJ consumed, accused remains active, recipient bribe notification delivered, no public recipient leak.
- EFJ: guilty verdict without EFJ still follows normal conviction transfer routing.
- Vest: blocked gunshot creates no trial, consumes vest, routes vest value to attacker, and keeps attacker hidden from public notice.
- Notebook: dead-player view remains read-only and does not leak owner-private write capability back into active play.
