# Documentation Layout

- `documentation/deployment/`: operational runbooks for production deployment and recovery.
- `documentation/discussion/`: evolving design discussion, decisions, open questions, and working notes.
- `documentation/features/`: formal feature specs that define expected behavior for implementation and testing.

Rule:
- Game/server behavior must come from code and formal feature specs.
- Discussion docs are context, not executable authority.
- JSON API error behavior follows RFC 7807 Problem Details via shared decorators/exceptions in `project/mobboss_apps/mobboss/`.
