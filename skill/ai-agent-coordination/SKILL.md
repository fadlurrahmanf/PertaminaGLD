---
name: ai-agent-coordination
description: Coordinate multiple AI coding agents in one shared repository with pre-action activity logging and narrow ownership claims. Use when Codex, Claude, or other agents may work in the same repo; when activity logs, ownership files, AGENTS.md, CLAUDE.md, resume/progress docs, or parallel-work rules exist; before non-trivial edits, commits, branch/worktree changes, deployments, hardware access, database changes, service restarts, live-system access, or long-running tasks; or whenever work could conflict across files, branches, ports, devices, servers, or runtime state.
---

# AI Agent Coordination

Use this skill to prevent overlapping AI-agent work. Discover local rules, read peer activity, write a narrow pre-action claim, work only inside that claim, and close the log with the result.

## Required Sequence

1. Locate coordination rules before non-trivial work.
   - Prefer repository files over memory or assumptions.
   - Check likely files: `AGENTS.md`, `AI_WORKFLOW_RULES.md`, `CLAUDE.md`, `README.md`, `docs/resume.md`, `docs/progress.md`.
   - Check activity logs in `ActivityAI/` first, then root-level legacy paths:
     - `ActivityAI/codexactivity.md`
     - `ActivityAI/claudeactivity.md`
     - `ActivityAI/*activity*.md`
     - `codexactivity.md`
     - `claudeactivity.md`
     - `*activity*.md`

2. Read the relevant activity logs.
   - Identify active owners, pending owners, recently completed work, claimed files, claimed branches, claimed worktrees, hardware ports, services, databases, and deployment targets.
   - Treat explicit user instructions as the highest local override, but still mention conflicts if the override is risky.

3. Decide whether the task is safe.
   - Simple read-only lookup: proceed after reading the minimum relevant coordination context.
   - File edit: verify no active owner has claimed the same file or directory.
   - Hardware, service, database, deployment, or long-running job: verify no active owner has claimed that runtime resource.
   - Ambiguous ownership or active conflict: ask the user before editing or running state-changing commands.

4. Write the pre-action claim before touching state.
   - Use the current agent's own log if it exists.
   - If the repo defines a specific log location, follow it.
   - If not, prefer `ActivityAI/<agent>activity.md`.
   - Write `PLANNED` or `ACTIVE` before file edits, repo-state changes, hardware access, deploys, database changes, service restarts, branch/worktree changes, or long-running work.
   - State the exact files, directories, branch/worktree, hardware ports, services, database tables, or deployment targets you intend to touch.
   - Keep the claim as small as possible.
   - Do not claim broad areas such as "backend" or "firmware" when exact files are known.

5. Work only inside the claim.
   - If the needed scope changes, update the activity log before expanding work.
   - Do not touch files, devices, services, or databases outside the logged claim without a new `PLANNED` or `ACTIVE` entry.

6. Close the activity log.
   - Write or update `DONE` when work completes.
   - Write or update `BLOCKED` when user input or an external state change is needed.
   - Include verification results, skipped checks, or the exact next command when useful.

## Conflict Rules

- Do not edit files currently marked active by another agent unless the user explicitly directs the override.
- Do not run uploads, flashes, hardware monitors, deploys, migrations, or service restarts against resources claimed by another agent.
- If another agent's ownership is marked done, read the surrounding notes and proceed only if the current request is compatible.
- If two instructions conflict, follow the newest explicit user instruction and document the conflict in the activity log.
- If a repo has immutable baseline files, never edit them directly unless the user explicitly revokes that rule.
- Avoid hidden assumptions. Prefer exact paths, exact commands, exact ports, exact tables, and exact branch/worktree names.

## Activity Entry Shape

Use the repository's existing format when one exists. If none exists, use this compact shape:

```text
[YYYY-MM-DD HH:MM TZ] STATUS | ACTION | FILES/RESOURCES | RESULT/NEXT
```

Recommended statuses:

- `PLANNED`: scope is claimed but work has not changed files/state yet.
- `ACTIVE`: work is in progress or a long-running command/resource is in use.
- `DONE`: work completed and verification status is known.
- `BLOCKED`: work cannot proceed without user input or external state change.

Log these actions:

- Created, edited, moved, deleted, generated, formatted, or validated files.
- Ran commands that changed repo state, external runtime state, database contents, hardware firmware, services, branches, commits, or deploys.
- Claimed or released files, directories, devices, ports, services, branches, worktrees, or database tables.
- Found a conflict and asked the user to decide.

Do not over-log harmless reads unless the repository or user explicitly asks for every agent action. When the repository or user requires pre-action logging, `PLANNED` or `ACTIVE` is step zero before non-trivial work, not an after-the-fact note.

## Coordination With Worktrees

When parallel work is substantial:

1. Prefer separate branches or worktrees for each agent.
2. Record each agent's worktree path, branch, and ownership.
3. Avoid concurrent edits to the same file.
4. Merge by diff/review after both scopes are complete.
5. Never assume a remote exists; check before discussing push or pull request flows.

## Coordination With Hardware Or Live Systems

Treat these as exclusive resources unless the repo says otherwise:

- Serial/COM ports.
- Firmware upload targets.
- Physical boards and devices.
- Local services and ports.
- Databases and migrations.
- Node-RED or workflow deploy targets.
- MQTT brokers and live topics.
- Production or bench environments.

Before using one, check activity logs for an active claim and log your own `PLANNED` or `ACTIVE` claim if safe.

## References

- For reusable patterns and examples, read `references/activity-log-patterns.md` only when creating or revising activity-log conventions.
