# SPEC-023: ADT Continuous Synchronization

**Author:** GEMINI (DevOps_Engineer)
**Date:** 2026-02-12
**Status:** APPROVED
**References:** AI_PROTOCOL.md, SPEC-014 (DTTP)

---

## 1. Problem Statement

Agents operating within the ADT Framework modify code and configuration. While
the ADS logs *intent* and *authorization*, the actual code artifacts are only
persisted if the agent explicitly remembers to commit and push.

The human governor has mandated a "non-negotiable" policy: all agent work must
be constantly submitted to GitHub. This ensures:
1.  **Off-site Backup:** No work is lost if the local machine fails.
2.  **Auditability:** Every file change maps to a git commit.
3.  **Collaboration:** Multiple agents/humans can see changes immediately.

## 2. Proposed Solution

Integrate a **Continuous Synchronization Engine** directly into the DTTP Gateway.
Every successful file modification action (`edit`, `create`, `delete`, `patch`)
automatically triggers a git commit and push sequence.

### 2.1 Commit Policy

- **Trigger:** Immediate upon successful file write.
- **Scope:** The specific file(s) modified by the action.
- **Message Format:** `[ADT] <Action> <File> - <Agent> (<Role>)`
  - Example: `[ADT] edit adt_core/dttp/actions.py - GEMINI (Backend_Engineer)`
- **Author:** The git commit author should reflect the agent if possible, or
  a generic `adt-bot` identity if not.

### 2.2 Push Policy

- **Trigger:** Immediately after commit.
- **Target:** Current branch, remote `origin`.
- **Failure Handling:**
  - If push fails (e.g., network down, conflict), log a warning to ADS but
    **do not roll back** the file modification.
  - Retry on next action.

## 3. Implementation

### 3.1 New Module: `adt_core/dttp/sync.py`

A `GitSync` class that handles shell execution of git commands.

```python
class GitSync:
    def __init__(self, project_root):
        ...
    def commit_and_push(self, file_path, message):
        # git add file_path
        # git commit -m message
        # git push origin HEAD
```

### 3.2 Update `ActionHandler`

Modify `adt_core/dttp/actions.py` to call `GitSync` after success.

```python
def _handle_edit(self, params):
    # ... write file ...
    # ... on success:
    self.git_sync.commit_and_push(file_path, f"edit {rel_path}")
```

## 4. Performance Considerations

- **Latency:** Git operations add overhead (0.5s - 2s). This is acceptable for
  the safety guarantee.
- **Concurrency:** Multiple agents writing might cause git lock contention.
  `GitSync` should implement a simple retry mechanism or lock.

## 5. Security

- Git credentials must be available to the `dttp` service user (ssh-agent or
  credential helper).
- No secrets in commit messages.

---

**Human Mandate:** "Insure that all agents submit to github constantly non negotiable!"
