# Role Ability Implementation Matrix

Last updated: 2026-03-22

## Purpose

This document is the authoritative planning matrix for the remaining role-ability placeholder cards in gameplay.

It answers two questions:

1. Which roles should expose activated powers in the current gameplay architecture?
2. Which roles should remain passive-only summary cards whose behavior is already covered by phase, succession, leadership, or economy rules?

## Decision Summary

- Live activated powers in the current phase:
  - `Don`
  - `Under Boss`
  - `Kingpin`
  - `Deputy`
  - `Sheriff`
  - `Captain`
  - `Lieutenant`
  - `Sergeant`
  - `Detective`
  - `Inspector`
  - `Police Officer`
  - `Merchant`
  - `Street Thug`
- Keep the existing automatic summary cards as automatic-only:
  - `Chief of Police`
  - `Mob Boss`
  - `Knife Hobo`
- Classify every remaining placeholder role except `Deputy`, `Sheriff`, `Captain`, `Lieutenant`, `Sergeant`, `Detective`, `Inspector`, `Police Officer`, `Merchant`, and `Street Thug` as `passive-only` for the next implementation slice.
- Do not add new gameplay commands, DTOs, endpoints, or `ParticipantPowerStateSnapshot` fields for the remaining placeholder roles (excluding `Deputy`, `Sheriff`, `Captain`, `Lieutenant`, `Sergeant`, `Detective`, `Inspector`, `Police Officer`, `Merchant`, and `Street Thug`) in the next slice.
- Replace grouped placeholder metadata with explicit per-role informational metadata only.

## Why This Is the Current Authority

- Current feature docs and decisions define rank, succession, trial flow, merchant economy, and a small set of explicit role powers.
- They do not define additional player-triggered powers for the remaining named titles.
- The current code already treats many named roles as rank/flavor variants inside broader Police, Mob, and Merchant systems.
- Adding new activated powers now would require inventing new rules rather than implementing existing ones.

## Code-Facing Rules

- `passive-only` means:
  - no role-specific POST action
  - no new inbound command
  - no new request DTO
  - no new mutation endpoint
  - no new persisted power-state field
  - role card remains `kind="info"` in the current UI pattern
- `automatic hook` means behavior may still change based on authoritative game state:
  - leadership succession
  - accused-selection eligibility
  - conviction transfer routing through current faction leader
  - merchant-goal evaluation
  - existing economy commands

## Matrix

| Role | Classification | Trigger Window | Allowed Targets | Visibility / Privacy | State / Ledger Impact | Implementation Notes | Required Tests |
|---|---|---|---|---|---|---|---|
| `Deputy` | activated (once/game) | information phase only | any alive participant except self | activation and custody notices to moderator + deputy + target only; no public role leak | target receives 5-minute murder immunity; attempted murder still starts trial but target stays alive and no transfer; power use persisted on deputy | role card exposes target selector + timer; separate custody timer panel for moderator/deputy/target | domain tests for activation/use-limit + attempted-murder branch; view/template context test for deputy action state + timer visibility |
| `Sheriff` | activated (twice/game) | any phase while game is `in_progress` | none (self-activation) | reveal visible to Sheriff only; moderator already has jury visibility in moderator projections | no ledger mutation; reveals latest known jury roster for 60 seconds without vote data | role card exposes `View Jury Log`; fails with `No jury history yet` before first jury assignment | domain tests for two-use cap + no-history failure; view context test for actionable panel and temporary reveal |
| `Captain` | activated (once/game) | any phase while game is `in_progress` | any alive participant except self | activation/timer visible to captain + target + moderator; transaction-cancel notices also sent to affected counterparties | blocks target money actions (buy/sell/gift send/receive) for 10 minutes; cancels pending sale/gift/money offers involving target; no direct ledger entry | role card exposes target selector + timer; blocked actions surface freeze message with target username | domain tests for activation/cancellation + blocked transactions; view context test for captain panel/timer visibility |
| `Lieutenant` | activated (once/game) | any phase while game is `in_progress` | none (self-activation) | reveal visible to Lieutenant only; moderator already has broader authoritative visibility | no ledger mutation; stores alive faction counts (Police/Mob/Merchant) for temporary reveal | role card exposes `Information Briefcase`; reveal persists for 60 seconds with no countdown | domain test for once-per-game + alive counts; view context test for lieutenant reveal state |
| `Sergeant` | activated (once/game) | information phase only | any alive participant except self | capture/timer visible to Sergeant + target + moderator only | target is treated as unavailable for interactions/powers while captured; one active capture at a time; no ledger mutation; capture auto-releases if required leader has no replacement | role card exposes `Capture` target selector + timer; if no replacement leader exists, notifies court-ordered release | domain tests for activation + blocking + auto-release branch; view context test for sergeant panel/timer |
| `Detective` | activated (once/game) | any phase while game is `in_progress`; blocked if Detective is currently captured/in custody | any participant, including alive, dead, jailed, or self | reveal visible to Detective only; no moderator/target/public notice; no countdown shown | no ledger mutation; persists a 60-second private reveal of the target's last 3 player-to-player transactions; records new accepted sale, money-gift, and item-gift history going forward; old sale + money-gift history is backfilled from ledger where possible | role card exposes `Start Investigation` target selector; result shows local timestamp, sender, recipient, money amount, item name, and transaction type; excludes central-supply and other system-initiated transfers | domain tests for once-per-game + jailed-target + captured-blocked + legacy-ledger backfill; view context test for private reveal state; sqlite round-trip for persisted reveal/transaction history |
| `Inspector` | activated (once/game) | any phase while game is `in_progress`; blocked if Inspector is currently captured/in custody | any dead or jailed participant except self | reveal visible to Inspector only; no moderator/target/public notice; no countdown shown | no ledger mutation; persists a 60-second private reveal of the selected target's role name | role card exposes `Record Inspection` target selector; fails with `No jail or morgue records available yet.` if no dead/jailed targets exist | domain tests for once-per-game + dead/jailed targeting + no-record failure + captured-blocked; view context test for private reveal state; sqlite round-trip for persisted reveal state |
| `Police Officer` | activated (once/game) | information, accused selection, or active trial voting before all jury votes are submitted; blocked if Police Officer is currently captured/in custody | none (self-activation) | Police Officer and moderator are always notified of the outcome; alive police beneficiaries are notified when they receive funds; overridden normal inheritance recipient is notified when confiscation blocks their transfer; no public notice beyond normal trial outcome | on the next guilty verdict, if the officer is still alive and EFJ does not trigger, jailed inventory is liquidated to cash, the officer receives the confiscation cut, and the remainder is redistributed to other alive police; if officer is inactive, EFJ triggers, no guilty verdict occurs, or no resources exist, the armed effect is consumed and resolved with notices | role card exposes `Activate Confiscation`; while pending, the card shows the next guilty verdict is armed; successful confiscation suppresses the usual single-recipient conviction-transfer private notice | domain tests for successful redistribution + officer-inactive cancellation + EFJ cancellation; view context test for actionable pending state; sqlite round-trip for persisted pending/used state |
| `Cop` | passive-only | automatic during accused-selection and Police succession | none | same as above | may advance in Police responder / leader chain; no direct role-specific ledger mutation | explicit info card; no action control | same pattern |
| `Enforcer` | passive-only | no extra role trigger beyond core Mob gameplay and succession | none | self sees own role; moderator sees full role state; no public leak | may become active Mob leader through succession; if promoted before conviction routing, leader-owned transfer rules apply | keep informational only despite the title implying force; no power is specified in current rules | view-context test for explicit metadata; template test confirms no action form |
| `Made Man` | passive-only | no extra role trigger beyond core Mob gameplay and succession | none | same as above | may become active Mob leader through succession; no direct role-specific ledger mutation until promoted | explicit info card; no action control | same pattern |
| `Gangster` | passive-only | no extra role trigger beyond core Mob gameplay and succession | none | same as above | may become active Mob leader through succession; no direct role-specific ledger mutation until promoted | explicit info card; no action control | same pattern |
| `Street Thug` | activated (once/game) | any phase while game is `in_progress`; blocked if Street Thug is currently captured/in custody | any alive participant except self and captured targets | Street Thug, target, and moderator are notified of the result; no public notice | transfers exactly $100 from target to Street Thug if target has at least that much money; otherwise no money moves; power is consumed either way; successful steals add a player-to-player ledger entry | role card exposes `Steal` target selector; failed steals still consume the power and surface failure notices | domain tests for success + insufficient-funds consumption; view context test for actionable panel; sqlite round-trip for persisted used state |
| `Felon` | passive-only | no extra role trigger beyond core Mob gameplay and succession | none | same as above | may become active Mob leader through succession; no direct role-specific ledger mutation until promoted | explicit info card; no action control | same pattern |
| `Merchant` | activated (once/game) | information phase only; blocked if Merchant is currently captured/frozen or not alive | one currently active central-supply catalog item | Merchant and moderator are notified of the wholesale purchase; no public role leak | central-supply purchase at a 30% discount from the current listed price, rounded to normal money rules; purchase still deactivates the shared stock item and records a central-supply purchase ledger entry at the reduced amount | role card exposes `Wholesale Order` item selector; success grants inventory at the discounted acquisition value and marks the power used | domain tests for pricing + use-limit/insufficient-funds behavior; view-context test for actionable panel; sqlite round-trip for persisted used state |
| `Arms Dealer` | automatic start-loadout | game launch only | none | Arms Dealer sees the startup notification; moderator already has authoritative inventory visibility | one Tier 1 gun is removed from shared central supply stock and placed into Arms Dealer inventory at launch; no later activation state or ledger entry | role card is informational only and explains the automatic starting gun cache | domain test for launch inventory + stock removal; view-context test for explicit automatic metadata |
| `Smuggler` | activated (once/game) | information phase only; blocked if Smuggler is currently captured | one alive non-self participant who is not currently captured | result is private to Smuggler, target, and moderator only | one truly random eligible inventory item moves from target to Smuggler if available; items already tied up in pending sale/gift offers are excluded; no money ledger entry; successful theft is persisted in player transaction history for Detective visibility | role card exposes `Smuggle` target selector; if target has no eligible items, the power is still consumed and only private failure notices are sent | domain tests for successful theft + no-item consumption + Detective transaction history; view-context test for actionable panel + stolen-item detective label; sqlite round-trip for persisted used state |
| `Gun Runner` | activated (once/game, timed) | information phase only; blocked if Gun Runner is currently captured | none (self-activation) | activation and bonus-payout notices are private to Gun Runner and moderator only | starts a 3-minute window; every accepted player-to-player sale during the active window pays an extra 30% system bonus based on the accepted sale price, rounded to the normal nearest-$10 rule; bonus is ledgered from `central_supply`; buyer is not charged extra | role card exposes `Charisma` activation and live countdown; frozen accounts do not block activation but still block actual transactions while the timer runs | domain tests for activation + active-window bonus + expiry; view-context test for active countdown state; sqlite round-trip for persisted used/expiry state |
| `Supplier` | passive-only | automatic during information-phase economy play and boundary win checks | none | same as above | existing economy flows already mutate ledger; no extra role-specific transfer route | explicit info card; no action control | same pattern |

## Implementation Consequences

The next UI/code slice should do the following and no more:

1. Replace grouped placeholder metadata in `gameplay/views.py` with explicit per-role informational metadata.
2. Keep `project/mobboss_apps/gameplay/templates/gameplay/_superpower_card.html` informational for passive-only roles; expose activated actions only for the explicitly approved powered roles.
3. Do not add new service mutations or new persisted role-power state for passive-only roles.
4. Add view/template tests proving each explicit role mapping renders the intended state (passive-only roles with no action form, powered roles with actionable controls).

## Deferred Rule-Making Boundary

If the project later wants a new activated role power for any currently passive-only role, that work must start with:

1. an explicit feature-rule update,
2. a decision-log entry,
3. a matrix update in this file,
4. then domain/API/UI/test implementation.
