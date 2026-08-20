# SPEC-109 — Deprecation of `adt-agy-probe` PreToolUse Hook

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE, 2026-08-23)
**Authority:** Operator verbal approval, 2026-08-23 22:00 UTC
**Relates to:** SPEC-061 (Antigravity Multi-Model Worker Plane), SPEC-108 (Sandbox Hardening)

**Intent:** Restore the ADT Console's ability to spawn functional Gemini architect sessions inside the Antigravity CLI, so cross-model orchestration promised by SPEC-061 is actually usable end-to-end.

**Triggering Event:** On 2026-08-23 at 22:56 UTC, the operator invoked `/summon architect` inside Antigravity and every subsequent tool call was blocked by a failed `adt-agy-probe-global` PreToolUse hook (evidence: `~/.gemini/antigravity-cli/log/cli-20260823_204654.log`). The spawned Gemini agent was completely non-operational.

**Success Condition:** A fresh `/summon architect` inside Antigravity CLI produces zero `adt-agy-probe` hook-failure entries in `~/.gemini/antigravity-cli/log/cli-*.log`, and the spawned Gemini architect can execute `run_shell`, `view_file`, and `list_dir` calls without pre-tool denial.

---

## 1. Overview

The `adt-agy-probe` PreToolUse hook was landed as part of SPEC-061 Phase 6.1
to capture the structure of `PreToolHookArgs` from Google's Antigravity CLI.
The probe achieved its purpose and evidence was collected in
`/tmp/agy_probe.jsonl`. The hook has since been left in place and, following
Antigravity's upgrade to a sandboxed execution model (documented in
SPEC-108), the probe has become a **hard block on every tool call** made by
Gemini architect sessions spawned via the ADT Console.

---

## 2. Symptom (Observed 2026-08-23 22:56 UTC)

Antigravity CLI log (`~/.gemini/antigravity-cli/log/cli-20260823_204654.log`):

```
pre-tool hook failed: JSON hook "jsonhook__adt-agy-probe-global_PreToolUse_0_0" failed:
command failed: exit status 2, stderr:
python3: can't open file
'/home/human/Projects/adt-framework/adt_sdk/plugins/adt-agy-probe/hooks/pre_tool.py':
[Errno 2] No such file or directory
```

Every `/summon <role>` invoked inside Antigravity was blocked. The spawned
Gemini architect could not read, edit, or search any file.

---

## 3. Root Cause

Two absolute-path hook registrations reference the host filesystem path to
the probe script:

| Registration | File |
|---|---|
| `adt-agy-probe-global` | `~/.gemini/config/hooks.json` |
| `adt-agy-probe` | `~/.gemini/config/plugins/adt-agy-probe/hooks.json` |

Both point to `/home/human/Projects/adt-framework/adt_sdk/plugins/adt-agy-probe/hooks/pre_tool.py`.

Per SPEC-108 §3, Antigravity mounts the project at `/project` inside its
sandbox. The host path `/home/human/Projects/adt-framework/...` **does not
resolve inside the sandbox**, so `python3` cannot open the file → exit 2 →
Antigravity treats the PreToolUse hook as deny.

The probe script itself is coded to always return `allow_tool: true` — the
block is a side-effect of the sandbox path mismatch, not intended policy.

---

## 4. Decision

Remove the two runtime hook registrations. Leave the plugin source tree
(`adt_sdk/plugins/adt-agy-probe/`) in place as SPEC-061 evidence.

### 4.1 Files Removed

| Path | Reason |
|---|---|
| `~/.gemini/config/hooks.json` | Sole content is the `adt-agy-probe-global` block; deletion removes the block entirely. |
| `~/.gemini/config/plugins/adt-agy-probe/hooks.json` | Sole content is the `adt-agy-probe` block; deletion removes the block entirely. |

Backups are created at `<path>.bak_spec109_20260823` before deletion.

### 4.2 Files Preserved

- `adt_sdk/plugins/adt-agy-probe/hooks/pre_tool.py` — SPEC-061 evidence.
- `adt_sdk/plugins/adt-agy-probe/plugin.json` — evidence.
- `~/.gemini/config/plugins/adt-agy-probe/hooks/hooks.json` — uses portable
  `${extensionPath}` interpolation, unaffected by the sandbox path issue.

---

## 5. Non-Goals

- Portable hook path replacement (deferred; if the probe ever needs to run
  again, it must use `${extensionPath}` per Antigravity plugin convention).
- Removal of the probe from the `adt_sdk/plugins/` tree.

---

## 6. Acceptance Criteria

1. Running `/summon architect` in Antigravity CLI no longer emits the
   `adt-agy-probe` hook-failure error.
2. Gemini architect sessions spawned via the ADT Console can execute
   `run_shell`, `view_file`, `grep_search`, `list_dir`, `write_to_file`
   without pre-tool block.
3. `~/.gemini/antigravity-cli/log/cli-*.log` files created after this SPEC
   contain zero `adt-agy-probe` hook-failure entries.

---

## 7. Rollback

Restore either `.bak_spec109_20260823` file back to its original path.
