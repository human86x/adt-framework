# SPEC-014: Digital Transformation Transfer Protocol (DTTP) Implementation

**Status:** APPROVED
**Priority:** HIGH
**Owner:** Systems_Architect + Human
**Created:** 2026-02-05
**Revised:** 2026-02-05 (v2.0 -- Level 3 Privilege-Separated Architecture)
**References:** ADT Whitepaper (Sheridan, 2026), ADT_CONSTITUTION.md, AI_PROTOCOL v3.0
**Framework Origin:** ADT Section 2 -- "The Future of Digital Practice Management"

---

## 1. Purpose

This spec defines the implementation of the **Digital Transformation Transfer Protocol (DTTP)** for OceanPulse. DTTP is the structural enforcement layer that makes ADT governance **physically impossible to bypass** through OS-level privilege separation, replacing the current trust-based model where agents self-report compliance.

### 1.1 The Problem

Today, OceanPulse agents comply with ADT because they are instructed to in prompts. The enforcement hooks check jurisdiction and locks, but:

1. **Action and logging are decoupled** -- an agent edits a file, then logs to the ADS as a separate step. Nothing prevents edit-without-logging.
2. **Spec validation is self-reported** -- agents claim they checked the spec. The hooks do not verify this.
3. **The "Grave Violation" rule** detects missing logs **after the fact**, not before the action.
4. **Bash bypasses hooks entirely** -- agents can use shell commands to write files, SSH to remote hosts, or FTP to production without any hook interception.
5. **Credentials are world-readable** -- `MEMORY_BANK.md` contains SSH passwords and FTP credentials accessible to any agent.

This is governance by honour system. During this session, the Systems_Architect violated ADT Article II Section 2.1 by implementing artifacts of an unapproved spec -- and was caught by the human, not by the system. This proves that behavioural compliance fails even with the best intentions.

### 1.2 Enforcement Levels

| Level | Mechanism | What it prevents | Proven insufficient? |
|-------|-----------|-----------------|---------------------|
| 1. Behavioural | Prompt instructions | Nothing -- agent chooses to comply | YES (architect violation, 2026-02-05) |
| 2. Hook-based | Pre-action hooks | Accidental violations via standard tools | YES (Bash bypass, remote write bypass) |
| **3. Privilege-separated** | **OS permissions + network rules** | **ALL bypasses -- agent physically cannot write** | **TARGET** |

### 1.3 What DTTP Changes

```
WITHOUT DTTP (current):
  Agent decides -> Agent checks spec (voluntary) -> Agent acts -> Agent logs (voluntary)
  Agent can also: SSH to Pi, FTP to production, Bash write to filesystem (no checks)

WITH DTTP (Level 3):
  Agent requests action -> DTTP validates spec -> DTTP executes + logs atomically -> or DENIES
  Agent CANNOT: write locally, SSH anywhere, FTP anywhere (OS-enforced)
```

The agent never bypasses governance because it **physically lacks the ability to act** outside DTTP.

### 1.4 Scope

This spec covers the **OceanPulse-scale DTTP** -- a single-machine, privilege-separated execution gateway covering local filesystem writes and remote operations (SSH, FTP). It does NOT implement the full enterprise DTTP vision (network transport layer, cross-organisation orchestration). That is for future scale-up.

### 1.5 No Self-Governance

Per the whitepaper: *"DTTP functions as an open-source application layer... DTTP enforces compliance without governing itself."*

DTTP reads rules from `specs.json` and `jurisdictions.json`. It **never writes** to these files. Policy is defined by humans through SDD. If DTTP could modify its own rules, the entire security model collapses.

---

## 2. Architecture

### 2.1 Three-User Privilege Model

```
┌──────────────────────────────────────────────────────────────────┐
│  HUMAN (user: human)                                             │
│                                                                  │
│  Full filesystem access. Full network access.                    │
│  Approves specs. Works normally. Launches AI tools as "agent".   │
│  Maintains DTTP config. Break-glass recovery.                    │
│                                                                  │
│  Launch command:  sudo -u agent claude                           │
│                   sudo -u agent gemini                           │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  AGENT (user: agent)                                             │
│                                                                  │
│  READ-ONLY access to project directory.                          │
│  NO outbound SSH (port 22 blocked by iptables).                  │
│  NO outbound FTP (port 21 blocked by iptables).                  │
│  CANNOT read credentials file (/etc/dttp/secrets.json).          │
│  CAN call: dttp request (the ONLY write interface).              │
│                                                                  │
│  Write path:  dttp request --action edit --file X --spec Y ...   │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  DTTP (user: dttp)                                               │
│                                                                  │
│  WRITE access to project directory.                              │
│  OWNS credentials (/etc/dttp/secrets.json, mode 600).            │
│  OWNS SSH keys for remote hosts.                                 │
│  Outbound network allowed (SSH, FTP).                            │
│  Validates: spec + jurisdiction + locks + role authorisation.    │
│  Logs EVERY action atomically to ADS.                            │
│  Fail-closed: any validation failure = DENY.                     │
│                                                                  │
│  Runs as: setgid service or sudo rule for agent user.            │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Attack Surface Coverage

| Vector | Current (Level 1) | DTTP Level 3 |
|--------|-------------------|--------------|
| Local file write (Edit/Write tools) | Unrestricted | **Blocked** -- agent user has no write permission |
| Local file write (Bash echo/cat) | Unrestricted | **Blocked** -- agent user has no write permission |
| SSH to Pi Main (192.168.43.37) | Unrestricted | **Blocked** -- iptables drops port 22 for agent |
| SSH to Pi Health (192.168.43.49) | Unrestricted | **Blocked** -- iptables drops port 22 for agent |
| FTP to oceanpulse.pt | Unrestricted | **Blocked** -- iptables drops port 21 for agent + no credentials |
| curl/wget to external services | Unrestricted | **Blocked** -- outbound restricted by iptables |
| Read credentials from MEMORY_BANK.md | Unrestricted | **Blocked** -- credentials moved to /etc/dttp/secrets.json (mode 600, owner dttp) |
| Modify enforcement hooks | Unrestricted | **Blocked** -- hooks owned by dttp, read-only for agent |
| Modify DTTP gateway/config | Unrestricted | **Blocked** -- _cortex/dttp/ owned by dttp |

### 2.3 File Structure

```
/etc/dttp/
├── secrets.json          # Credentials (SSH, FTP) -- owner: dttp, mode 600
└── dttp.conf             # Gateway configuration -- owner: dttp, mode 644

_cortex/dttp/
├── gateway.py            # The DTTP validation + execution gateway
├── specs.json            # Machine-readable spec index (read by gateway)
├── jurisdictions.json    # Role-to-path jurisdiction map (read by gateway)
├── shadow.log            # Shadow mode decision log (Phase 3)
└── README.md             # Developer documentation
```

### 2.4 Spec Index Format (`specs.json`)

```json
{
  "version": "1.0",
  "specs": {
    "SPEC-002": {
      "title": "Component Integration & Serial Protocol",
      "status": "active",
      "roles": ["Embedded_Engineer", "Network_Engineer"],
      "paths": ["firmware/", "bridge/", "comms/"],
      "action_types": ["file_edit", "file_create", "file_read"]
    },
    "SPEC-003": {
      "title": "ADT Operational Dashboard",
      "status": "active",
      "roles": ["Frontend_Engineer", "Overseer"],
      "paths": ["adt_panel/", "_cortex/ads/"],
      "action_types": ["file_edit", "file_create", "adt_sync"]
    }
  }
}
```

### 2.5 Secrets Format (`/etc/dttp/secrets.json`)

```json
{
  "ssh": {
    "pi_main": {"host": "192.168.43.37", "user": "lab", "pass": "***"},
    "pi_health": {"host": "192.168.43.49", "user": "router", "pass": "***"}
  },
  "ftp": {
    "oceanpulse": {"host": "ftp.oceanpulse.pt", "user": "oceanpul", "pass": "***"}
  }
}
```

This file is readable ONLY by the `dttp` user. Agents cannot access it.

---

## 3. Gateway Operations

### 3.1 Local File Operations

Agent requests a file operation through DTTP:

```bash
dttp request \
  --action edit \
  --file firmware/main_mega.ino \
  --content "$(cat /tmp/agent_staging/edit_payload.diff)" \
  --agent CLAUDE \
  --role Embedded_Engineer \
  --spec_ref SPEC-002 \
  --session_id claude_embedded_20260205
```

Gateway performs:
1. **Validate** -- spec active? role authorised? jurisdiction match? lock free?
2. **Log pre-action** -- write "pending" event to ADS (atomic, before file touch)
3. **Execute** -- apply the file modification (gateway has write permission)
4. **Log post-action** -- write "success" or "failure" event to ADS
5. **Return** -- result to agent (JSON: allowed/denied, event_id)

### 3.2 Remote Operations (SSH)

Agent requests a remote deployment:

```bash
dttp request \
  --action deploy \
  --target pi_main \
  --file firmware/main_mega/main_mega.ino \
  --agent CLAUDE \
  --role Embedded_Engineer \
  --spec_ref SPEC-002 \
  --session_id claude_embedded_20260205
```

Gateway performs:
1. **Validate** -- same 5 checks as local
2. **Log pre-action** to ADS
3. **Connect** -- using credentials from `/etc/dttp/secrets.json` (agent never sees these)
4. **Execute** -- SCP file, run arduino-cli, etc.
5. **Log post-action** with remote output
6. **Return** -- result to agent

### 3.3 Remote Operations (FTP / Panel Sync)

```bash
dttp request \
  --action ftp_sync \
  --target oceanpulse \
  --files "data.json,panel.js,index.html,style.css,about.html" \
  --agent CLAUDE \
  --role Overseer \
  --spec_ref SPEC-003 \
  --session_id claude_overseer_20260205
```

### 3.4 Validation Checks (All Operations)

Five checks, in order. All must pass.

| # | Check | Source of Truth | New? |
|---|-------|----------------|------|
| 1 | Role assigned | Request parameters | Existing |
| 2 | Jurisdiction match | `jurisdictions.json` | Existing (now machine-readable) |
| 3 | No lock conflict | `_cortex/active_tasks/` | Existing |
| 4 | Spec exists and is active | `specs.json` | **NEW** |
| 5 | Spec authorises role | `specs.json` | **NEW** |

### 3.5 Fail-Closed Design

If the gateway crashes, encounters an error, or cannot validate:
- **DEFAULT: DENY**
- Log the failure to ADS if possible
- The agent cannot proceed
- Human must investigate

The system must never fail-open.

---

## 4. Atomic Action-Log Coupling

### 4.1 The Problem

Currently: Agent acts (step 1) then logs (step 2). If step 2 fails or is skipped, the action happened but the ledger has no record.

### 4.2 The DTTP Solution

DTTP performs the action AND the logging. They are the same process. There is no way to have one without the other because the agent doesn't do either -- DTTP does both.

```
DTTP ALLOW flow:
  1. Log pre-action event to ADS (outcome: "pending")
  2. Perform the file write / SSH command / FTP upload
  3. Log post-action event to ADS (outcome: "success" or "failure")
  4. Return result to agent

DTTP DENY flow:
  1. Log denial event to ADS (outcome: "blocked", escalation: true)
  2. Return denial to agent
```

The agent receives the result but performs neither the action nor the logging.

### 4.3 Orphan Detection

A pre-action event without a matching post-action event in the same session indicates a gateway crash during execution. The Overseer flags these as anomalies requiring investigation.

---

## 5. Implementation Phases (Safe Development Path)

### CRITICAL CONSTRAINT

DTTP must be **fully built and tested** before the permission switch (Phase 4) activates. If permissions are changed prematurely, agents cannot write, which means they cannot build DTTP. **Deadlock.**

The solution: Phases 1-3 are built under the **current permission model** (agents have full write access). Phase 4 flips the switch only when everything is proven working.

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5
Build        Test        Shadow      Permissions  Live
(current     (current    (current    (NEW model   (enforced)
 perms)       perms)      perms)      activated)
```

**At any point before Phase 4, the system is unchanged. No risk.**
**Phase 4 is the single irreversible step. It has a rollback plan.**

---

### Phase 1: Build DTTP Components (No System Impact)

**Performed by:** DevOps_Engineer (under current permissions)

**Deliverables:**
- `_cortex/dttp/gateway.py` -- validation + execution gateway
- `_cortex/dttp/specs.json` -- populated from existing specs
- `_cortex/dttp/jurisdictions.json` -- populated from AI_PROTOCOL Section 4.1
- `/etc/dttp/secrets.json` -- credentials extracted from MEMORY_BANK.md
- `dttp` command wrapper (shell script that calls gateway.py with sudo)

**System impact:** ZERO. Files are created but nothing uses them yet. Agents continue working normally with current permissions.

---

### Phase 2: Unit Testing (No System Impact)

**Performed by:** DevOps_Engineer

**Tests:**
- Valid action (correct spec, role, jurisdiction) → ALLOW
- Wrong jurisdiction → DENY
- Inactive spec → DENY
- Wrong role for spec → DENY
- Lock conflict → DENY
- Missing spec_ref → DENY
- Gateway crash → DENY (fail-closed)
- Local file write via gateway → file modified + ADS event created
- SSH via gateway → remote command executed + ADS event created
- FTP via gateway → files uploaded + ADS event created

**System impact:** ZERO. Tests run against test data, not the live ADS.

---

### Phase 3: Shadow Mode (No System Impact)

**How it works:**
- Agents continue working normally (current permissions)
- A background process monitors file modifications in the project directory
- For each modification, shadow DTTP evaluates: "Would I have allowed this?"
- Decisions logged to `_cortex/dttp/shadow.log`
- Overseer reviews shadow log for false positives/negatives

**Run for:** Minimum 3 agent sessions across at least 2 different roles.

**Criteria to proceed:**
- Zero false denials (shadow would have blocked a legitimate action)
- All actual violations detected (shadow would have caught known issues)
- Human reviews shadow log and approves

**System impact:** ZERO. Shadow mode is observation only.

---

### Phase 4: Permission Switch (The Cutover)

**Performed by:** HUMAN ONLY (not agents, not DTTP)

This is the single step that activates Level 3. It is performed by the human directly, not through any AI agent.

**Pre-flight checklist (all must be YES):**
- [ ] gateway.py passes all unit tests
- [ ] Shadow mode ran 3+ sessions with zero false denials
- [ ] Human reviewed and approved shadow log
- [ ] Rollback procedure tested (see 5.1)
- [ ] AI tool configs (API keys, git) set up for agent user
- [ ] /etc/dttp/secrets.json populated and permissions verified

**Setup commands (run as human/root):**

```bash
# 1. Create users
sudo useradd -r -m -s /bin/bash agent
sudo useradd -r -m -s /bin/bash dttp

# 2. Transfer project ownership
sudo chown -R dttp:dttp /home/human/Projects/oceanpulse_phase_one/
sudo chmod -R u+rwX,g+rX,o+rX /home/human/Projects/oceanpulse_phase_one/

# 3. Credential isolation
sudo mkdir -p /etc/dttp
sudo cp secrets.json /etc/dttp/secrets.json
sudo chown dttp:dttp /etc/dttp/secrets.json
sudo chmod 600 /etc/dttp/secrets.json

# 4. Remove credentials from world-readable files
# (Human manually redacts MEMORY_BANK.md, replacing passwords with "[DTTP-MANAGED]")

# 5. Network restrictions for agent user
sudo iptables -A OUTPUT -m owner --uid-owner agent -p tcp --dport 22 -j DROP
sudo iptables -A OUTPUT -m owner --uid-owner agent -p tcp --dport 21 -j DROP

# 6. Allow agent to call DTTP via sudo
echo "agent ALL=(dttp) NOPASSWD: /home/human/Projects/oceanpulse_phase_one/_cortex/dttp/gateway.py" \
  | sudo tee /etc/sudoers.d/dttp

# 7. Set up agent user config (API keys, git identity)
sudo -u agent mkdir -p /home/agent/.claude /home/agent/.config
# Copy necessary config files...

# 8. Make iptables rules persistent
sudo apt install iptables-persistent
sudo netfilter-persistent save
```

**Verification:**

```bash
# Test: agent cannot write directly
sudo -u agent touch /home/human/Projects/oceanpulse_phase_one/test.txt
# Expected: Permission denied

# Test: agent cannot SSH
sudo -u agent ssh lab@192.168.43.37
# Expected: Connection dropped by iptables

# Test: agent cannot read secrets
sudo -u agent cat /etc/dttp/secrets.json
# Expected: Permission denied

# Test: agent CAN read project files
sudo -u agent cat /home/human/Projects/oceanpulse_phase_one/_cortex/MASTER_PLAN.md
# Expected: File contents displayed

# Test: agent CAN call DTTP
sudo -u agent sudo -u dttp python3 _cortex/dttp/gateway.py --action ping
# Expected: {"status": "ok"}
```

**System impact:** HIGH but controlled. This is the activation moment.

---

### 5.1 Rollback Procedure (Break Glass)

If DTTP malfunctions after Phase 4, the human restores full access in under 60 seconds:

```bash
# BREAK GLASS: Restore pre-DTTP permissions
sudo chown -R human:human /home/human/Projects/oceanpulse_phase_one/
sudo iptables -D OUTPUT -m owner --uid-owner agent -p tcp --dport 22 -j DROP
sudo iptables -D OUTPUT -m owner --uid-owner agent -p tcp --dport 21 -j DROP

# Agents can now be launched normally (as human user) with full access
claude    # Works as before
gemini    # Works as before
```

The rollback returns the system to the pre-DTTP state. No data is lost. The ADS, specs, and all project files remain intact.

---

### Phase 5: Live Enforcement

**Activation:**

```bash
# Launch AI tools under restricted user
sudo -u agent claude    # Claude Code runs as "agent"
sudo -u agent gemini    # Gemini CLI runs as "agent"
```

Agents discover they cannot write directly. Their workflow becomes:
1. Read files normally (read access is unrestricted)
2. Request writes through `dttp request` command
3. Request deployments through `dttp request --action deploy`
4. Request FTP syncs through `dttp request --action ftp_sync`

All operations are validated, executed, and logged by DTTP. The agent receives results but never touches the filesystem or network directly.

---

## 6. Impact on Agent Workflow

### 6.1 What Changes for Agents

| Operation | Before DTTP | After DTTP |
|-----------|-------------|------------|
| Read files | Direct (Read tool) | Direct (Read tool) -- **no change** |
| Edit files | Direct (Edit/Write tool) | `dttp request --action edit` |
| Create files | Direct (Write tool) | `dttp request --action create` |
| SSH to Pi | Direct (Bash: ssh) | `dttp request --action deploy --target pi_main` |
| FTP to panel | Direct (Bash: curl/ftp) | `dttp request --action ftp_sync --target oceanpulse` |
| Log to ADS | Direct (log.py) | **Automatic** -- DTTP logs as part of every operation |
| Read credentials | Direct (MEMORY_BANK.md) | **Cannot** -- credentials managed by DTTP |

### 6.2 What Stays the Same

- Reading any project file
- Analyzing code, planning, reasoning
- Running read-only Bash commands (ls, git log, git status, python --version)
- Inter-agent communication via `_cortex/requests.md` (via DTTP write request)
- ADS is still the single source of truth
- Specs still drive all work
- Jurisdiction rules unchanged (just enforced structurally now)

### 6.3 AI_PROTOCOL Update

After Phase 4, AI_PROTOCOL.md Section 1.1 changes from:

> "EVERY action you take MUST be logged to the ADS."

To:

> "All actions are logged automatically by DTTP. Agents do NOT log directly to the ADS. Request actions through the `dttp request` command. DTTP handles validation, execution, and logging atomically."

### 6.4 Agent Prompt Updates

The `/hive-<role>` and `/summon <role>` activation prompts must be updated to instruct agents:
- Use `dttp request` for all write operations
- Do NOT attempt direct file writes (they will fail with Permission Denied)
- Do NOT attempt SSH/FTP (connections will be dropped)
- Read operations remain unchanged

---

## 7. Relationship to Existing Components

| Component | Before DTTP | After DTTP |
|-----------|-------------|------------|
| `adt-enforce.sh` (hooks) | Enforces jurisdiction + locks | **Retired** -- DTTP replaces all hook functions |
| `log.py` (Safe Logger) | Called by agents voluntarily | Called by gateway.py internally (agents never call it) |
| `AI_PROTOCOL.md` | Behavioural rules (trust-based) | Structural rules (OS-enforced) |
| `events.jsonl` (ADS) | Written by agents | Written exclusively by DTTP |
| `specs/*.md` (Markdown) | Human-readable only | Indexed in machine-readable specs.json |
| `MEMORY_BANK.md` | Contains all credentials | Credentials redacted, replaced with "[DTTP-MANAGED]" |
| `firmware/deploy.sh` | Called directly by agents | **Retired** -- replaced by `dttp request --action deploy` |

---

## 8. Success Criteria

### 8.1 Structural (Level 3 Proof)

- [ ] Agent user CANNOT write any project file directly (OS permission denied)
- [ ] Agent user CANNOT SSH to any remote host (iptables drop)
- [ ] Agent user CANNOT FTP to any remote host (iptables drop)
- [ ] Agent user CANNOT read credentials (file permission denied)
- [ ] Agent user CANNOT modify DTTP config/gateway (file permission denied)
- [ ] Agent CAN read all project files
- [ ] Agent CAN request writes through DTTP
- [ ] DTTP correctly validates and executes authorised requests
- [ ] DTTP correctly denies and logs unauthorised requests

### 8.2 Functional

- [ ] All 5 validation checks work correctly
- [ ] Local file edit via DTTP produces correct file content + ADS event
- [ ] SSH deploy via DTTP flashes firmware + ADS event
- [ ] FTP sync via DTTP uploads panel files + ADS event
- [ ] Every denial logged with `escalation: true`
- [ ] Fail-closed on gateway error

### 8.3 Operational

- [ ] Gateway adds less than 500ms latency to file operations
- [ ] Rollback to pre-DTTP state takes under 60 seconds
- [ ] Agent workflow is functional (agents can still do their jobs)
- [ ] No false denials during 3+ session shadow mode test

### 8.4 ADT Whitepaper Alignment

- [ ] "DTTP executes only specification-authorised actions" -- PROVEN structurally
- [ ] "If an action is not recorded, it is not recognised" -- PROVEN (DTTP logs atomically)
- [ ] "Humans define intent, automation enforces" -- PROVEN (specs.json by humans, enforced by gateway)
- [ ] "Governance is an intrinsic system property" -- PROVEN (OS-level, not behavioural)

---

## 9. What DTTP Does NOT Do (Scope Limits)

1. **No network transport** -- This is a local privilege-separated gateway, not a distributed protocol. Enterprise DTTP-over-network is a future evolution.
2. **No full invocation chaining** -- Individual actions are validated, not entire process chains. Chain validation is a future evolution.
3. **No self-governance** -- DTTP reads rules from data files. It cannot modify its own config, specs.json, or jurisdictions.json. Policy comes from humans via SDD.
4. **No spec creation** -- Writing/approving specs remains a human + Systems_Architect function.
5. **No outbound HTTP restriction** -- Agents can still make outbound HTTP requests (needed for API access). Future: whitelist-based HTTP filtering.

---

## 10. Amendments

This spec may be amended as implementation reveals practical constraints. All amendments logged to ADS with `spec_ref: SPEC-014`.

---

## 11. ADT Whitepaper Traceability

| Whitepaper Concept | SPEC-014 Implementation |
|-------------------|------------------------|
| "DTTP executes only specification-authorised actions" | OS permissions ensure agent can ONLY act through DTTP gateway |
| "Operationalising intent and compliance without governing itself" | Gateway reads specs.json, cannot modify it |
| "Cryptographically linked chains" | All DTTP actions extend ADS hash chain |
| "If an action is not recorded, it is not recognised" | Logging is atomic with execution -- impossible to have one without the other |
| "Analogous to platforms such as Apache" | Local gateway with defined request interface |
| "Humans define intent... automation enforces" | specs.json authored by humans, enforced by OS + gateway |
| "Accountability by construction" | Every DTTP action records agent, role, spec, authority -- structurally, not voluntarily |
| "Continuous auditability" | ADS events are by-product of execution, not reconstructed after the fact |

---

*"Governance is an intrinsic system property, not an external overlay."*
*-- ADT Framework (Sheridan, 2026)*
