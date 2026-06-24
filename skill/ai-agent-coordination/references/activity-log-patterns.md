# Activity Log Patterns

Use these examples when a repository has no existing activity-log convention.

## Minimal File Layout

Prefer one shared folder:

```text
ActivityAI/
  codexactivity.md
  claudeactivity.md
```

Use root-level `codexactivity.md` or `claudeactivity.md` only as legacy fallback paths.

## Ownership Table

```markdown
## Current Ownership

| File / Area | Owner | Status | Notes |
|---|---|---|---|
| `src/api/routes.ts` | Codex | Active | Refactor auth route only |
| `docs/release.md` | Claude | Pending | Waiting for test results |
| COM10 firmware upload | None | Free | Last used 2026-06-19 09:12 |
```

## Action Log

```markdown
## Log

[2026-06-19 09:00 +07:00] PLANNED | Claim route refactor | `src/api/routes.ts` | No conflict found
[2026-06-19 09:01 +07:00] ACTIVE | Editing route validation | `src/api/routes.ts` | Scope logged before file edits
[2026-06-19 09:08 +07:00] DONE | Refactor route validation | `src/api/routes.ts`, `tests/api.test.ts` | `npm test` passed
[2026-06-19 09:10 +07:00] BLOCKED | Need database migration decision | `db/schema.sql` | Claude owns migration scope
```

## Claiming Rules

- Claim exact files or resources, not vague subsystems.
- Write `PLANNED` or `ACTIVE` before non-trivial actions when the repo requires pre-action logging.
- Mark claims done or released when complete.
- Include verification command results when available.
- Keep old entries append-only unless the repo explicitly permits cleanup.

## Conflict Questions

Ask a concrete question when blocked:

```text
Claude currently owns `db/schema.sql` as Active. Should I wait, make a separate proposal without editing, or override and update the activity log?
```

Avoid vague questions like:

```text
Should I handle the database stuff?
```
