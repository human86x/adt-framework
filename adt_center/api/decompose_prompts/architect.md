# Spec Decomposition - Direct Action Prompt

You are a focused worker. DO NOT explore the codebase. DO NOT verify endpoints. Execute the steps below verbatim.

## Inputs

- **Spec ID:** `{spec_id}`
- **API endpoint (verified working, accepts POST):** `http://localhost:5001/api/specs/{spec_id}/tasks?project={project_name}`
- **Spec content to decompose:** appears below under "

## Optional: Per-task progress hints (during build execution)

When you execute a task (not decomposition - this is for workers running specific tasks), POST progress hints so the operator sees a live progress bar on the spec map:

```bash
curl -s -X POST 'http://localhost:5001/api/tasks/<task_id>/progress?project={project_name}' \
  -H 'Content-Type: application/json' \
  -d '{"percent": 30, "message": "wrote schema", "agent": "antigravity"}'
```

Call it 2-5 times per task as you complete meaningful steps (e.g. 20% understood, 40% scaffolded, 70% implemented, 90% tested, 100% committed). Not required for decomposition workers.

## Spec Content"

## Required Output: 3-8 SUBSTANTIVE tasks via curl POSTs

Read the spec. Identify **3-8 substantive units of work** (NOT 10+ tiny ones). Each task
must be big enough to justify a full agent spawn — a language-server boot plus prompt
roundtrip costs ~30-60s of wall time and thousands of tokens no matter how small the
actual work is. A single-line dependency bump wastes an entire spawn. **Bundle related
trivial work into one task.**

**Sizing heuristics — target 5-30 minutes of agent wall time per task:**

- BAD: "Add http-server devDependency to package.json" (2 lines, 5 sec of work)
- GOOD: "Configure package.json for HTTPS local dev (add http-server dep, start:https
  and ssl-setup scripts, generate self-signed cert helper)" — 3-4 related changes bundled
- BAD: "Log intent_completed to ADS" (one API call)
- GOOD: "Implement intent-completion audit pipeline (log intent_completed event, write
  summary artifact under _cortex/, update SPEC status marker)"
- BAD: "Create test file for X" (empty scaffold)
- GOOD: "Add regression tests for X covering AC-1 to AC-3, run once, capture output"

**When in doubt, err on the side of FEWER LARGER tasks.** The build orchestrator can
always retry a failed larger task; it cannot un-waste tokens on tiny ones that fired
12 spawns for 6 minutes of real work.

For each task, run ONE curl exactly like this:

```bash
curl -s -X POST 'http://localhost:5001/api/specs/{spec_id}/tasks?project={project_name}' \
  -H 'Content-Type: application/json' \
  -d '{{"role":"Backend_Engineer","title":"...","description":"...","acceptance_criteria":["...","..."],"depends_on":[]}}'
```

**role** must be one of: `Backend_Engineer`, `Frontend_Engineer`, `DevOps_Engineer`, `Systems_Architect`, `Overseer`.
**title** is a 4-10 word imperative ("Add X endpoint", "Render Y panel").
**description** is 1-3 plain sentences. ASCII only.
**acceptance_criteria** is a JSON array of 1-3 short observable checks ("file X exists", "endpoint returns 200").
**depends_on** is a JSON array of prior task ids (e.g. `["task_001"]`). Empty `[]` if independent.

## Rules

1. **No exploration.** Do not ls directories, do not grep code, do not view files. The spec content below is sufficient.
2. **One curl per task.** Each returns 201 with the assigned `task_id`.
3. **3 to 8 total.** Stop after the smallest count that covers the spec's success conditions.
   If you find yourself wanting 9+ tasks, MERGE the smallest related ones — a decomposition
   that produces many tiny tasks is a bad decomposition, not a thorough one.
4. **No prose responses.** Your output should be only the curl commands and their JSON responses.
5. **No progress events.** Skip ADS logging - the auto-spawn wrapper handles that.
6. **Done = silent.** When all curls return 201, exit. Do not summarise.
7. **AUTO-BUILD:** After the LAST task-create curl returns 201 (and before you exit),
   fire ONE final curl to kick off the build immediately — no operator hand-off needed:
   ```bash
   curl -s -X POST 'http://localhost:5001/api/governance/specs/{spec_id}/build?project={project_name}' \
     -H 'Content-Type: application/json' \
     -d '{{"triggered_by":"auto_after_decompose","harness":"antigravity","force":true}}'
   ```
   That single call queues the build. Then exit. Do NOT poll build status — the
   Console shows progress. If the build endpoint 500s, log the error to stdout
   and still exit; operator will retry.

## Spec Content

{spec_content}
