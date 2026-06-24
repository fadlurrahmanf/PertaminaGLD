# AGENTS.md

## Repository Interaction Rules

For parallel AI-agent work, also read `ActivityAI/rules/AI_WORKFLOW_RULES.md`.

## Priority Order

1. Ask first.
2. Provide the most professional, technically sound solution.
3. Challenge risky, weak, incomplete, or unmaintainable directions with concrete reasoning.
4. Implement only after the important assumptions and approval points are clear.

## Agent Routing

- Use `GLD_Agent` automatically for non-trivial GLD context: GLD firmware, GLD design, gas sensor flow, ADS1256, nulling DAC, GLD LoRa payload, GLD power mode, GLD running/dataset/nulling modes, GLD MQTT dataset mode, GLD Modbus scaffold, and GLD-to-CH behavior from the GLD side.
- Use `CH_Agent` automatically for non-trivial CH context: CH firmware, CH design, dual-LoRa behavior, STAR receiver, MESH/TREE behavior, `AppFrame`, `typeFlags`, `NodeCache`, server pull, CH pending downlink, CH ACK/retry/failover, CH-to-CH, CH-to-Gateway, and GLD-to-CH behavior from the CH side.
- Use `GW_Agent` automatically for non-trivial Gateway context: Gateway firmware, MESH root behavior, CH-to-Gateway behavior, Gateway WiFi/LAN, HTTP API, MQTT bridge, root routing, Gateway-to-Server behavior, and Gateway board verification.
- Use `Server_Agent` automatically for non-trivial server context: Node-RED, MQTT broker/client flows, HTTP polling, AES-GCM decrypt, dedup, MySQL/storage, dashboard backend data, alarm routing, test/manual filtering, and server deployment.
- Use `Integration_Agent` automatically for non-trivial end-to-end context: GLD-CH-Gateway-Server test plans, COM-port bench setup, upload/monitor sequencing, cross-component protocol checks, acceptance gates, release readiness, and residual-risk reporting.
- When a task touches multiple components, use each relevant component agent, keep their findings separated first, then reconcile the integration recommendation in the main response.
- When a task is simple, such as listing files, answering a direct factual question, or making a tiny text edit, answer directly without spawning agents.
- If the current Codex surface cannot spawn custom agents automatically, follow the same routing mentally and state when a true subagent could not be used.

- For non-trivial work in this repository, ask the user many clarifying questions before making design, architecture, protocol, data-model, hardware, deployment, or UI decisions.
- Prefer a broad question set over silent assumptions. Group questions by topic such as scope, data, protocol, hardware, UI, backend, testing, deployment, and acceptance criteria.
- When the request is ambiguous, ask 10-25 concise questions if useful. More questions are acceptable when the task is large or the risk of misunderstanding is high.
- Ask especially many questions before creating new files, changing protocol behavior, changing database fields, editing firmware pins, changing API contracts, or deciding how GLD and CH components should communicate.
- If the user asks for a simple command, direct lookup, typo fix, or exact output format, keep the response direct and do not add unnecessary questions.
- If the user has already answered a topic, do not keep repeating the same question. Ask follow-up questions only when they unlock concrete implementation decisions.
- Asking comes first. After enough context is gathered, give the best technical recommendation rather than simply following the user's first idea.
- Professional solution means production-minded, maintainable, testable, observable where relevant, and aligned with real project constraints.
- If the user's requested approach is risky, incomplete, inefficient, hard to maintain, or conflicts with project evidence, say so directly and propose a better option with concrete reasoning.
- When there are multiple viable approaches, recommend one primary path, explain the tradeoffs briefly, and identify what decision still needs user approval.
- Do not agree just to be agreeable. Be collaborative, but keep engineering judgment independent.
- Update `docs/chat/fullchat.md` and `docs/chat/summary.md` only when the user explicitly says `save` or directly asks to save/update the chat context. Do not update those files on every prompt unless the user changes this rule again.
- **Resume file rule:** When the user says `save`, always update `docs/resume.md` together with the chat docs. The resume file must be self-contained and complete enough that a *different* AI agent (with no conversation history) can pick up the work exactly where it left off. It must include: current firmware versions, what was just implemented (with key file paths), what is pending (with exact commands), bench environment config, and rules that must remain active. Any AI starting a new session on this repo must read `docs/resume.md` first.
- **Auto-compact rule:** When context window usage reaches >= 50%, run `/compact` (or equivalent compact command) immediately before continuing. Do not wait until near the limit. If the runtime does not expose context usage automatically, compact proactively after any large output (long file reads, build logs, serial monitor dumps, or multi-file diffs).
- **Low usage/context rule:** If the current UI or runtime exposes remaining usage/context and it is below 10%, update `docs/chat/fullchat.md`, `docs/chat/summary.md`, and `docs/resume.md` before continuing any long-running, multi-step, or risky work. If automatic detection is not available, do this as soon as the user reports usage is below 10% or the assistant can clearly see the indicator. The save must capture current versions, changed files, test/deploy status, blockers, and exact next commands.
- When asking questions, make each question specific enough to answer without guessing. Avoid vague words such as "stored", "handled", or "integrated" unless the question states the exact location, layer, field, file, device, or runtime behavior being asked about.
- Do not edit imported original design files directly: `docs/design/gld/design.md` and `docs/design/ch/design.md`. Treat them as immutable source imports.
- If a design needs edits, create a copy in the same folder first, such as `design.draft.md` or `design.<topic>.draft.md`, and edit only that copy so the original and session-modified versions remain easy to compare.
- Use Indonesian by default when the user writes in Indonesian.
- **Activity log rule:** Before non-trivial work, read the peer activity log in `ActivityAI/` to check for conflicts (`ActivityAI/codexactivity.md` for Claude, `ActivityAI/claudeactivity.md` for Codex). Before changing files/state, using hardware/COM ports, deploying, touching databases, or running long work, write a `PLANNED` or `ACTIVE` entry in the current agent's own log (`ActivityAI/claudeactivity.md` for Claude, `ActivityAI/codexactivity.md` for Codex) with exact scope/files/resources. After work completes or blocks, append/update `DONE` or `BLOCKED` in the same log. Use format `[YYYY-MM-DD HH:MM] STATUS | ACTION | FILES` where the file uses that shape, and update the ownership table when taking or releasing ownership of a file/area/resource.
