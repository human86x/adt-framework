# SPEC-023: Git Persistence & Push Governance

**Status:** APPROVED
**Priority:** HIGH
**Owner:** Systems_Architect (spec), DevOps_Engineer (implementation)
**Created:** 2026-02-12
**References:** SPEC-014, SPEC-017, SPEC-020, REQ-002

---

## 1. Purpose

To ensure the permanence and integrity of the framework's development history. Currently, DTTP governs file writes but not their persistence in version control. This creates a "governance gap" where authorized changes can exist as unstaged local files without being committed or pushed, making the audit trail in ADS decoupled from the repository state.

This spec makes **git commit mandatory after file edits** and brings **git push under DTTP jurisdiction**.

---

## 2. Mandatory Session Persistence

### 2.1 Commit Requirement
Every agent session that produces file modifications MUST end with a `git commit` before the `session_end` event is logged to ADS.

- **Scope:** All tracked files in the repository.
- **Verification:** The `session_end` logic in the agent wrapper/console must check `git status --porcelain`. If unstaged or uncommitted changes exist (excluding ignored files), the session MUST NOT be closed until a commit is made.

### 2.2 Commit Message Schema
Commit messages must follow a standardized format to ensure traceability:

```
[<SPEC_ID>] <TASK_ID>: <Summary of changes>

Rationale: <Brief explanation>
ADS: <EVENT_ID_OF_LAST_ACTION>
Agent: <AGENT_NAME>
Role: <ROLE_NAME>
```

### 2.3 ADS Integration
The `session_end` ADS event MUST include the `commit_hash` of the final commit made during the session.

---

## 3. DTTP-Governed Git Actions

Git operations that interact with the remote repository or modify history are now governed actions within DTTP.

### 3.1 New Action Types

| Action Type | Description | Tier |
|-------------|-------------|------|
| `git_commit` | Create a local commit | 3 |
| `git_push` | Push commits to a remote repository | 2 (main) / 3 (others) |
| `git_tag` | Create a version tag | 2 |
| `git_merge` | Merge branches (especially into main) | 2 |

### 3.2 Authorization Rules

#### 3.2.1 `git_commit` (Tier 3)
- Authorized by the same spec that authorized the file edits.
- Standard jurisdiction check applies (must have jurisdiction over all modified files).

#### 3.2.2 `git_push` (Tier 2 for `main`)
- Pushing to the `main` branch is a **Tier 2 (Constitutional)** action.
- Requires a dedicated "Release" or "Integration" spec (e.g., SPEC-017 or a new SPEC-024).
- Requires `tier2_justification` in the DTTP request.
- Pushing to feature branches is Tier 3.

#### 3.2.3 `git_tag` (Tier 2)
- Tagging a release is a Tier 2 action.
- Requires explicit spec authorization.

---

## 4. Implementation Plan

### 4.1 Phase A: Action Handlers (DevOps_Engineer)
- Update `adt_core/dttp/actions.py` to add `_handle_git_commit`, `_handle_git_push`, `_handle_git_tag`.
- These handlers use the local `git` binary.
- Validation: `git_push` handler must verify the target branch and remote.

### 4.2 Phase B: SDK & Hook Support (Backend_Engineer)
- Update `adt_sdk/client.py` to add `git_commit()` and `git_push()` methods.
- Update `adt_sdk/hooks/` to intercept git commands if possible, or provide a dedicated `adt-git` wrapper.

### 4.3 Phase C: Console Enforcement (Frontend_Engineer)
- Update the Operator Console to detect uncommitted changes.
- Add a "Commit & Close" button to the session termination dialog.
- Display the current branch and commit status in the status bar.

---

## 5. Security & Isolation

- In production (Level 3 separation), only the `dttp` user has the SSH keys required to push to the remote repository.
- Agents (running as `agent` user) have no network access to GitHub and no local SSH keys. They MUST request a `git_push` through DTTP.

---

## 6. Acceptance Criteria

- [ ] `git_push` to `main` branch is denied by DTTP without Tier 2 authorization.
- [ ] ADS logs include `commit_hash` for `session_end` events.
- [ ] Attempting to end a session with uncommitted changes triggers a warning/block in the Console.
- [ ] Commit messages correctly reference Spec and Task IDs.

---

*"Version control is the memory of the code. ADT ensures that memory is as governed as the code itself."*