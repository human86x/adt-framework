# SPEC-027: Shatterglass Protocol (OS-Level Governance Enforcement)

**Status:** APPROVED
**Priority:** CRITICAL
**Owner:** Systems_Architect (spec), DevOps_Engineer + Backend_Engineer (implementation)
**Created:** 2026-02-13
**References:** SPEC-020 (Self-Governance Integrity), SPEC-014 (DTTP Level 3)
**Supersedes:** SPEC-020 Section 3 (Break-Glass Procedure)

---

## 1. Purpose

Upgrade the break-glass protocol from an honor-system manual procedure to an OS-enforced privilege escalation mechanism. Currently, SPEC-020 protects sovereign and constitutional paths at the application level -- DTTP *denies* requests, but agents could theoretically bypass DTTP via shell commands. This spec moves the protection to the filesystem itself: **agents cannot physically write to governed files, period.** Only when the human activates the Shatterglass Protocol does the system temporarily grant write credentials.

> "Application-level governance says 'you should not.' OS-level governance says 'you cannot.'"

---

## 2. Problem

### 2.1 Current State (SPEC-020)

```
Agent --[Write tool]--> DTTP Hook --[dry_run]--> DTTP Gateway
                                                      |
                                           [Check sovereign paths]
                                           [Check constitutional paths]
                                           [Check policy]
                                                      |
                                              ALLOW or DENY
```

The agent's Write/Edit tool is intercepted by the DTTP hook. But:

- If the agent uses **Bash** to write files, the hook is not triggered
- If the DTTP service is **down**, the hook fails-closed -- but the agent could restart without the hook
- If the agent **modifies hook settings**, it removes its own enforcement
- Application-level protection is a locked door with the key taped to the frame

### 2.2 Required State (This Spec)

```
Agent (OS user: agent) --[any method]--> Filesystem
                                              |
                                    [OS permission check]
                                    agent has READ-ONLY on:
                                      - config/*.json
                                      - _cortex/AI_PROTOCOL.md
                                      - _cortex/MASTER_PLAN.md
                                      - _cortex/ads/events.jsonl
                                      - adt_core/dttp/*.py
                                      - adt_core/ads/*.py
                                              |
                                       PERMISSION DENIED
                                              |
                                    (no bypass possible)
```

The OS itself blocks the write. No hook needed. No application logic needed. The agent cannot write to these files through any tool, any shell command, any method.

---

## 3. Architecture

### 3.1 User Model

Three OS users (extending SPEC-014 Phase 4):

| User | Purpose | File Access |
|------|---------|-------------|
| `human` | The operator. Runs the ADT Panel, approves specs, configures governance. | Full read/write everywhere |
| `dttp` | The enforcement service. Runs DTTP on :5002. Writes to governed files on behalf of authorized requests. | Read/write on governed files. Owns ADS log. |
| `agent` | AI agents (Claude, Gemini). Runs in constrained environment. | **Read-only** on governed files. Read/write on Tier 3 paths within jurisdiction. |

### 3.2 File Permission Tiers

#### Tier 1: Sovereign Files (Human-Only Write)

Owner: `human:human`, permissions: `644` (human rw, everyone else read-only)

```
config/specs.json           human:human  644
config/jurisdictions.json   human:human  644
config/dttp.json            human:human  644
_cortex/AI_PROTOCOL.md      human:human  644
_cortex/MASTER_PLAN.md      human:human  644
```

Neither `agent` nor `dttp` can write to these. Only the human. The Governance Configurator (SPEC-026) runs as the human user via the ADT Panel.

#### Tier 2: Constitutional Files (DTTP-Only Write)

Owner: `dttp:dttp`, permissions: `644` (dttp rw, everyone else read-only)

```
adt_core/dttp/gateway.py    dttp:dttp    644
adt_core/dttp/policy.py     dttp:dttp    644
adt_core/dttp/service.py    dttp:dttp    644
adt_core/ads/logger.py      dttp:dttp    644
adt_core/ads/integrity.py   dttp:dttp    644
adt_core/ads/crypto.py      dttp:dttp    644
```

The `agent` user cannot write to these. The `dttp` user can, but only through the DTTP gateway's Tier 2 elevated authorization (SPEC-020 Section 2.2). The human can always write (has sudo or direct access).

#### Tier 2.5: ADS Event Log (Append-Only)

Owner: `dttp:dttp`, special permissions

```
_cortex/ads/events.jsonl    dttp:dttp    664 (append via DTTP service only)
```

The `agent` user can read the ADS log but not write to it. All ADS writes go through the DTTP service (which runs as `dttp`). This prevents agents from:
- Tampering with audit history
- Injecting false events
- Breaking the hash chain

#### Tier 3: Regular Files (Jurisdiction-Governed)

Owner: `dttp:dttp`, permissions: `664` (dttp rw, group rw, others read)

The `agent` user is in the `dttp` group and can write to Tier 3 files -- but only those within their DTTP-validated jurisdiction. In development mode, the DTTP hook enforces this at the application level. In production mode, the DTTP service writes on behalf of the agent (the agent never touches the file directly).

---

## 4. The Shatterglass Protocol

### 4.1 What It Is

A controlled, audited, temporary privilege escalation that allows the `dttp` user to write to Tier 1 sovereign files. Named "shatterglass" because activating it is deliberate, visible, and irreversible (the audit trail permanently records the activation).

### 4.2 When to Invoke

- DTTP is down and cannot be repaired through normal Tier 2 authorization
- A sovereign config file is corrupted and must be repaired
- The governance rules themselves need emergency modification
- The hash chain is broken and the ADS log needs healing

### 4.3 Activation Sequence

**Step 1: Human initiates via ADT Panel or CLI**

The human clicks "Shatterglass" in the Governance page (SPEC-026) or runs:

```bash
adt shatterglass activate --reason "DTTP policy lockout, all requests denied"
```

This command:
1. Prompts for confirmation: "This will temporarily grant write access to sovereign files. Type SHATTERGLASS to confirm."
2. Logs a `shatterglass_activated` event to ADS (appended by the `human` user directly, not through DTTP)
3. Generates a **time-limited credential token** (default: 15 minutes)
4. Temporarily changes file permissions on sovereign files:
   ```bash
   chmod 664 config/specs.json config/jurisdictions.json config/dttp.json
   chmod 664 _cortex/AI_PROTOCOL.md _cortex/MASTER_PLAN.md
   ```
5. Starts a **watchdog timer** that auto-revokes after the time limit

**Step 2: Human (or DTTP) makes the repair**

During the shatterglass window, the `dttp` user (and by extension, DTTP-authorized requests) can write to sovereign files. The human can also write directly.

All writes during the shatterglass window are logged with elevated audit flags:
```json
{
  "action_type": "shatterglass_write",
  "shatterglass_session": "<session_id>",
  "tier": 1,
  "escalation": true
}
```

**Step 3: Human deactivates (or timer expires)**

```bash
adt shatterglass deactivate
```

This:
1. Restores file permissions to read-only:
   ```bash
   chmod 644 config/specs.json config/jurisdictions.json config/dttp.json
   chmod 644 _cortex/AI_PROTOCOL.md _cortex/MASTER_PLAN.md
   ```
2. Logs `shatterglass_deactivated` event with duration and list of files modified
3. Invalidates the credential token
4. Triggers an automatic integrity check (hash chain verification)

**Step 4: Overseer audit (next session)**

The Overseer reviews:
- Duration of the shatterglass window
- Files modified during the window
- Whether changes were minimal and justified
- Hash chain integrity after deactivation

### 4.4 Auto-Expiry Safety Net

If the human forgets to deactivate, the watchdog timer restores permissions automatically. Default: 15 minutes. Configurable up to 60 minutes. After auto-expiry:

```json
{
  "action_type": "shatterglass_auto_expired",
  "duration_seconds": 900,
  "files_modified_during_window": ["config/specs.json"],
  "reason": "Timer expired without explicit deactivation"
}
```

### 4.5 Agent Exclusion

**Agents CANNOT activate the Shatterglass Protocol.** The activation command:
- Requires interactive terminal confirmation (type "SHATTERGLASS")
- Must run as the `human` OS user (not `agent`, not `dttp`)
- Checks `whoami` and refuses if not `human`
- Even if an agent somehow calls `adt shatterglass activate`, the OS permission to `chmod` sovereign files belongs to `human` only

---

## 5. Development vs Production Mode

### 5.1 Development Mode (Current)

In development, everyone runs as the same OS user (`human`). OS-level enforcement is not active. Protection is application-level only (DTTP hooks + gateway).

The Shatterglass Protocol is **not needed** in development mode because there are no OS-level restrictions to escalate past. DTTP still enforces sovereign path rejection at the application level per SPEC-020.

### 5.2 Production Mode

In production (after running the setup script), OS-level permissions are active:

```
human  -> full access (sovereign)
dttp   -> read/write on Tier 2+3, read-only on Tier 1
agent  -> read-only on Tier 1+2, jurisdiction-governed on Tier 3
```

The Shatterglass Protocol is the only way to temporarily grant `dttp` write access to Tier 1 files.

### 5.3 Transition

The setup script (`setup_shatterglass.sh`) transitions from development to production:

1. Create OS users (`agent`, `dttp`) if not exist
2. Set file ownership per tier classification
3. Set file permissions per tier classification
4. Install the `adt shatterglass` CLI command
5. Configure the watchdog timer service
6. Run integrity verification
7. Log `production_mode_activated` to ADS

---

## 6. Implementation Tasks

| Task | Description | Assigned To |
|------|-------------|-------------|
| task_067 | `adt shatterglass activate/deactivate` CLI commands | Backend_Engineer |
| task_068 | Watchdog timer service (auto-expiry of shatterglass window) | Backend_Engineer |
| task_069 | `setup_shatterglass.sh` -- OS user creation, file ownership, permissions | DevOps_Engineer |
| task_070 | ADS event types: shatterglass_activated, shatterglass_write, shatterglass_deactivated, shatterglass_auto_expired | Backend_Engineer |
| task_071 | ADT Panel "Shatterglass" button on Governance page with confirmation dialog | Frontend_Engineer |
| task_072 | Overseer audit extensions for shatterglass sessions | Systems_Architect |
| task_073 | Integration tests: permission enforcement, activation/deactivation, auto-expiry, agent exclusion | Backend_Engineer + DevOps_Engineer |

---

## 7. Acceptance Criteria

- [ ] In production mode, `agent` user cannot write to any Tier 1 or Tier 2 file via any method
- [ ] In production mode, `dttp` user cannot write to Tier 1 files (sovereign) under normal operation
- [ ] `adt shatterglass activate` temporarily grants `dttp` write access to Tier 1 files
- [ ] Shatterglass activation requires interactive confirmation ("type SHATTERGLASS")
- [ ] Shatterglass auto-expires after configurable timeout (default 15 min)
- [ ] All file modifications during shatterglass window are logged to ADS
- [ ] `adt shatterglass deactivate` restores read-only permissions and runs integrity check
- [ ] Agents (OS user `agent`) cannot activate shatterglass
- [ ] Overseer can audit shatterglass sessions via ADS query
- [ ] Development mode continues to work without OS-level restrictions

---

## 8. Security Analysis

### 8.1 Attack Vectors Closed

| Attack | Before (SPEC-020) | After (SPEC-027) |
|--------|-------------------|-------------------|
| Agent uses Bash to edit config/specs.json | DTTP hook not triggered, write succeeds | OS permission denied, write fails |
| Agent kills DTTP service then writes | No enforcement, write succeeds | OS permission still enforced, write fails |
| Agent modifies hook settings to remove enforcement | Hook removed, write succeeds | OS permission still enforced, write fails |
| Agent edits gateway.py to remove sovereign path list | Tier 2 check (application level) | OS permission denied (Tier 2 = dttp-owned) |
| Agent tampers with ADS log | Application-level protection only | ADS owned by dttp, agent has read-only |

### 8.2 Remaining Trust Assumptions

- The `human` OS user is trusted (they are the sovereign)
- The `dttp` OS user's code is reviewed before deployment (Tier 2 authorization)
- The OS itself is not compromised (kernel, filesystem integrity)
- WSL on Windows inherits Windows user permissions -- this works in WSL but the exact permission model should be validated

---

## 9. Compatibility

### 9.1 Linux (Native)

Full support. Standard Unix permissions (`chown`, `chmod`). The `setup_shatterglass.sh` script handles everything.

### 9.2 WSL (Windows Subsystem for Linux)

WSL 2 supports Linux file permissions natively on the Linux filesystem (`/home/...`). Files on Windows mounts (`/mnt/c/...`) do not support Linux permissions -- the project MUST reside on the Linux filesystem for Shatterglass to work.

### 9.3 macOS

Full support. Same Unix permission model. Users created via `dscl` instead of `useradd`.

### 9.4 Development Mode (Any Platform)

No OS-level restrictions. Shatterglass is dormant. Application-level DTTP enforcement only.

---

*"Application security is a request. OS security is a command."*
