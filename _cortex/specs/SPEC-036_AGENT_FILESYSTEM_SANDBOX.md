# SPEC-036: Agent Filesystem Sandbox

**Author:** CLAUDE (Systems_Architect)
**Date:** 2026-02-25
**Status:** APPROVED
**Approved:** 2026-02-25 by Human
**Origin:** REQ-026 (DevOps_Engineer)
**References:** SPEC-031 (External Project Governance), SPEC-027 (Shatterglass),
SPEC-014 (DTTP), SPEC-021 (Operator Console), ADT Whitepaper (Sheridan, 2026)

---

## 1. Problem Statement

When agents are spawned via the ADT Console for any project (external or framework),
they have **unrestricted filesystem access**. The DTTP hook only intercepts write-class
tools (Write, Edit, NotebookEdit for Claude; write_file, replace for Gemini). All other
tools -- Read, Glob, Grep, Bash -- operate with the full privileges of the OS user.

**Current attack surface:**

| Tool | Governed? | Risk |
|------|-----------|------|
| Write/Edit | Yes (DTTP hook) | Jurisdiction-checked |
| Read | No | Can read any file on the system |
| Glob | No | Can enumerate any directory |
| Grep | No | Can search any file content |
| Bash | No | Can read, write, execute anything the OS user can |

This means an agent assigned to Project A can:
1. Read Project B's source code, secrets, and environment files
2. Read the ADT Framework's own governance artifacts (`_cortex/specs/`, `config/`)
3. Write anywhere via `Bash(echo "..." > /arbitrary/path)`
4. Access SSH keys, cloud credentials, API tokens in `~/.ssh/`, `~/.aws/`, etc.
5. Read other projects' DTTP configurations and governance state

> "A governance framework that enforces write jurisdiction but allows unrestricted
> reads is enforcing half a policy." -- Sheridan principle: governance is intrinsic,
> not an overlay.

---

## 2. Design Principles

1. **Defense in depth**: Multiple independent layers, each sufficient to prevent
   a class of escape. No single bypass should grant full access.
2. **Proportional enforcement**: Tier 3 (development) uses application-level
   sandboxing. Tier 1 (production/Shatterglass) adds OS-level enforcement.
3. **Zero-trust agent model**: Agents are assumed adversarial within their
   capability set. Sandbox boundaries are not "hints" -- they are hard walls.
4. **Framework-project separation**: An agent working on an external project
   must NEVER see or access the ADT Framework's internal state.
5. **Minimal viable sandbox first**: Ship the application-layer sandbox (Phase A)
   immediately. OS-level hardening (Phase B) follows.

---

## 3. Architecture

### 3.1 Sandbox Layers

```
+------------------------------------------------------------------+
|  Layer 3: OS-Level (Tier 1 / Shatterglass)                       |
|  - Linux mount namespaces via unshare(2)                         |
|  - Bind-mount only project root into agent's filesystem view     |
|  - Network namespace restricts to project DTTP port only         |
|  - Agent runs as unprivileged OS user (sudo -u agent)            |
+------------------------------------------------------------------+
|  Layer 2: Agent CLI Configuration (Tier 3 / Development)         |
|  - Claude Code: allowedDirectories / blockedDirectories          |
|  - Gemini CLI: equivalent sandbox configuration                  |
|  - Generated per-session before agent process starts             |
+------------------------------------------------------------------+
|  Layer 1: DTTP Hook (existing)                                   |
|  - Write/Edit tools validated against jurisdiction + spec         |
|  - Path resolution via os.realpath() prevents symlink escapes    |
+------------------------------------------------------------------+
|  Layer 0: Environment Sanitization                               |
|  - HOME redirected to project-scoped temp directory              |
|  - PATH stripped of framework-specific entries                   |
|  - No ADT_FRAMEWORK_ROOT or equivalent leaked                   |
+------------------------------------------------------------------+
```

### 3.2 Per-Session Sandbox Configuration

The PTY spawner (`adt-console/src-tauri/src/pty.rs`) generates a sandbox
configuration **before** launching the agent process. This is the critical
enforcement point -- once the agent is running, it is too late to restrict it.

---

## 4. Phase A: Application-Layer Sandbox (Tier 3)

**Goal:** Restrict agent filesystem access using Claude Code and Gemini CLI's
own configuration mechanisms, without requiring OS-level changes.

### 4.1 Per-Session Settings Generation

Before spawning an agent session, the PTY spawner must:

1. Create a temporary sandbox directory: `<project_root>/.adt/sandbox/<session_id>/`
2. Generate agent-specific configuration inside it
3. Set environment variables pointing the agent CLI to use these configs
4. Launch the agent process

### 4.2 Claude Code Sandbox

**File:** `<project_root>/.adt/sandbox/<session_id>/.claude/settings.json`

```json
{
  "permissions": {
    "allow": [
      "Bash(python3:*)",
      "Bash(pytest:*)",
      "Bash(pip:*)",
      "Bash(npm:*)",
      "Bash(git:*)"
    ],
    "deny": [
      "Bash(curl:*)",
      "Bash(wget:*)"
    ]
  },
  "allowedDirectories": [
    "<project_root>"
  ]
}
```

**Environment:**
- `CLAUDE_CONFIG_DIR=<project_root>/.adt/sandbox/<session_id>/.claude`
  (or equivalent mechanism to redirect Claude Code's settings lookup)

**Effect:** Claude Code will refuse Read/Write/Glob/Grep operations on paths
outside `<project_root>`. Bash commands that reference external paths will be
blocked by the CLI's own sandbox enforcement.

### 4.3 Gemini CLI Sandbox

**File:** `<project_root>/.adt/sandbox/<session_id>/.gemini/settings.json`

```json
{
  "sandbox": {
    "allowedDirectories": ["<project_root>"]
  },
  "hooks": {
    "BeforeTool": [...]
  }
}
```

**Environment:**
- `GEMINI_CONFIG_DIR=<project_root>/.adt/sandbox/<session_id>/.gemini`

**Note:** If Gemini CLI does not support `allowedDirectories` natively, the
DTTP hooks must be extended to intercept ALL tool calls (not just write-class),
performing path validation on every file access. This is a fallback, not the
preferred approach.

### 4.4 Environment Sanitization

The PTY spawner must set these environment variables for sandboxed sessions:

```
HOME=<project_root>/.adt/sandbox/<session_id>/home
TMPDIR=<project_root>/.adt/sandbox/<session_id>/tmp
ADT_SANDBOX=1
ADT_SANDBOX_ROOT=<project_root>
ADT_PROJECT_DIR=<project_root>
DTTP_URL=http://localhost:<project_port>
```

The spawner must **remove** from the agent's environment:
```
ADT_FRAMEWORK_ROOT  (if set)
CLAUDE_PROJECT_DIR  (replace with ADT_PROJECT_DIR)
GEMINI_PROJECT_DIR  (replace with ADT_PROJECT_DIR)
```

The spawner must **not pass through**:
- `SSH_AUTH_SOCK` (prevents SSH key access)
- `AWS_*`, `GCP_*`, `AZURE_*` (prevents cloud credential access)
- Any variable containing paths outside `<project_root>`

### 4.5 Bash Tool Hardening

The per-session `.claude/settings.json` should use the `permissions.deny` list
to block dangerous Bash patterns:

```json
{
  "permissions": {
    "deny": [
      "Bash(cat /etc/*)",
      "Bash(ls /home/*)",
      "Bash(find / *)",
      "Bash(curl:*)",
      "Bash(wget:*)",
      "Bash(ssh:*)",
      "Bash(scp:*)"
    ]
  }
}
```

**Limitation:** This is a blocklist approach and cannot cover all escape vectors.
It reduces the surface area but is not a hard boundary. Phase B provides the
hard boundary via OS namespaces.

### 4.6 Hook Extension for Read Tools

Extend the DTTP hooks to intercept Read/Glob/Grep when `ADT_SANDBOX=1`:

**Claude hook (`claude_pretool.py`):**
Add matchers: `Read|Glob|Grep`

When `ADT_SANDBOX=1`:
1. Extract the target path from the tool input
2. Resolve via `os.realpath()`
3. If path is outside `ADT_SANDBOX_ROOT`, return `{"decision": "block"}`
4. Log `sandbox_read_blocked` to ADS

**Gemini hook (`gemini_pretool.py`):**
Add matchers: `read_file|list_files|search_files`

Same logic as Claude hook.

---

## 5. Phase B: OS-Level Sandbox (Tier 1 / Shatterglass)

**Goal:** Hardware-enforced isolation using Linux kernel namespaces. An agent
physically cannot access files outside its sandbox, regardless of what tools
or shell commands it uses.

### 5.1 Prerequisites

- Shatterglass production mode enabled (`~/.adt/production_mode` flag)
- `agent` OS user created (`setup_shatterglass.sh`)
- Linux kernel with user namespace support (CONFIG_USER_NS=y, standard on
  all modern distributions)

### 5.2 Namespace Isolation

The PTY spawner wraps the agent command in an `unshare` + mount namespace:

```bash
unshare --mount --map-root-user --fork -- /bin/bash -c '
  # Create a minimal filesystem view
  mount --make-rprivate /

  # Bind-mount project root to a clean location
  mkdir -p /sandbox/project
  mount --bind <project_root> /sandbox/project

  # Bind-mount essential system directories (read-only)
  mount --rbind /usr /sandbox/usr -o ro
  mount --rbind /lib /sandbox/lib -o ro
  mount --rbind /lib64 /sandbox/lib64 -o ro
  mount --rbind /bin /sandbox/bin -o ro
  mount --rbind /etc/alternatives /sandbox/etc/alternatives -o ro

  # Pivot root
  cd /sandbox
  pivot_root . old_root
  umount -l /old_root

  # Drop into project directory as agent user
  cd /project
  exec sudo -u agent <agent_command> <args>
'
```

**Effect:** The agent's entire filesystem view consists of:
- `/project/` -- the governed project (read-write via DTTP)
- `/usr/`, `/lib/`, `/bin/` -- system binaries (read-only)
- Nothing else -- no `/home/`, no other projects, no framework

### 5.3 Network Namespace

```bash
unshare --net -- /bin/bash -c '
  # Create loopback
  ip link set lo up

  # Only allow traffic to project DTTP port
  iptables -A OUTPUT -d 127.0.0.1 -p tcp --dport <project_port> -j ACCEPT
  iptables -A OUTPUT -d 127.0.0.1 -p tcp --dport <panel_port> -j ACCEPT
  iptables -A OUTPUT -j DROP
'
```

**Effect:** The agent can only communicate with its own project's DTTP service
and the Panel (for SCR submission). No internet access, no access to other
projects' services.

### 5.4 Fallback: bubblewrap (bwrap)

If `unshare` requires root privileges (some hardened kernels disable user
namespaces), use `bubblewrap` as an alternative:

```bash
bwrap \
  --ro-bind /usr /usr \
  --ro-bind /lib /lib \
  --ro-bind /lib64 /lib64 \
  --ro-bind /bin /bin \
  --bind <project_root> /project \
  --tmpfs /tmp \
  --dev /dev \
  --proc /proc \
  --chdir /project \
  --unshare-net \
  --die-with-parent \
  -- sudo -u agent <agent_command> <args>
```

---

## 6. Sandbox Lifecycle

### 6.1 Session Start

```
Console UI                    PTY Spawner                    Agent Process
    |                             |                               |
    |-- create_session() -------->|                               |
    |                             |-- mkdir sandbox dir           |
    |                             |-- generate settings.json      |
    |                             |-- sanitize environment        |
    |                             |-- [Phase B: setup namespace]  |
    |                             |-- spawn agent process ------->|
    |                             |                               |-- reads sandbox settings
    |                             |                               |-- restricted filesystem
```

### 6.2 Session End

```
Agent Process                 PTY Spawner                    Cleanup
    |                             |                               |
    |-- exit ------------------>  |                               |
    |                             |-- [Phase B: namespace exits]  |
    |                             |-- rm -rf sandbox dir -------->|
    |                             |-- log session_end to ADS      |
```

### 6.3 Framework Self-Governance Exception

When the Console spawns an agent session for the **ADT Framework project itself**
(detected by matching `project_root == framework_root`), the sandbox is relaxed:

- `allowedDirectories` includes the framework root (same as project root)
- Environment sanitization still applies (no cloud creds, no SSH keys)
- DTTP hooks still enforce jurisdiction within the framework
- Phase B namespace is NOT applied (framework agents need broader access for
  governance operations)

This exception is justified: the framework governs itself recursively. Its agents
ARE the governance mechanism. Sandboxing them from their own governance artifacts
would prevent self-governance.

---

## 7. Implementation Tasks

### Phase A (Application-Layer Sandbox)

| Task | Role | Description |
|------|------|-------------|
| task_138 | DevOps_Engineer | Implement per-session sandbox directory creation and cleanup in `pty.rs` |
| task_139 | DevOps_Engineer | Implement Claude Code `settings.json` generation with `allowedDirectories` in `pty.rs` |
| task_140 | DevOps_Engineer | Implement Gemini CLI sandbox config generation in `pty.rs` |
| task_141 | DevOps_Engineer | Implement environment sanitization in `pty.rs` (HOME redirect, variable filtering) |
| task_142 | Backend_Engineer | Extend `claude_pretool.py` to intercept Read/Glob/Grep when `ADT_SANDBOX=1` |
| task_143 | Backend_Engineer | Extend `gemini_pretool.py` to intercept read tools when `ADT_SANDBOX=1` |
| task_144 | Backend_Engineer | Add sandbox status to `GET /api/sessions` response |
| task_145 | DevOps_Engineer | Write integration tests: agent cannot read outside project root |
| task_146 | DevOps_Engineer | Write integration tests: agent cannot write outside project via Bash |

### Phase B (OS-Level Sandbox)

| Task | Role | Description |
|------|------|-------------|
| task_147 | DevOps_Engineer | Implement `unshare` mount namespace wrapper in `pty.rs` |
| task_148 | DevOps_Engineer | Implement network namespace with DTTP port allowlist |
| task_149 | DevOps_Engineer | Add `bubblewrap` fallback for kernels without user namespaces |
| task_150 | DevOps_Engineer | Write integration tests: namespace-escaped paths are inaccessible |
| task_151 | DevOps_Engineer | Update `setup_shatterglass.sh` to install bubblewrap if needed |

---

## 8. Security Considerations

### 8.1 Known Limitations of Phase A

- **Bash escape**: The `permissions.deny` blocklist cannot cover all shell
  patterns. An agent can construct paths dynamically:
  `Bash(python3 -c "open('/etc/passwd').read()")`.
  This is why Phase B exists.
- **Agent CLI bugs**: If Claude Code or Gemini CLI have bugs in their
  `allowedDirectories` enforcement, the sandbox leaks. Layer 1 (DTTP hooks)
  provides partial backup.
- **Symlink attacks**: `os.realpath()` in hooks resolves symlinks, but an
  agent could create a symlink inside the project pointing outside, then read
  it via a tool that does not go through hooks. Phase A hook extension for Read
  tools mitigates this.

### 8.2 Phase B Guarantees

- **Kernel-enforced**: Mount namespaces cannot be escaped without CAP_SYS_ADMIN,
  which the agent user does not have.
- **No bypass via Bash**: Even `Bash(cat /etc/passwd)` fails because `/etc/passwd`
  is not mounted in the namespace.
- **No network escape**: iptables rules in the network namespace prevent all
  outbound connections except to the project's DTTP port.

### 8.3 Trust Boundaries

```
TRUSTED (human-controlled):
  - Console UI (Tauri webview)
  - PTY spawner (Rust code in adt-console/src-tauri/)
  - Namespace setup scripts
  - DTTP service process

UNTRUSTED (agent-controlled):
  - Everything inside the agent session
  - All tool calls
  - All Bash commands
  - All file operations
```

---

## 9. Acceptance Criteria

1. **Phase A:**
   - Agent spawned for external project cannot `Read` files outside project root
   - Agent cannot `Grep`/`Glob` outside project root
   - Agent cannot access `~/.ssh/`, `~/.aws/`, or framework `_cortex/` via any tool
   - `HOME` environment variable points to sandbox directory, not user home
   - Framework self-governance sessions remain unrestricted within framework root
   - Sandbox directories are cleaned up on session end

2. **Phase B:**
   - Agent's filesystem view contains ONLY project root and essential system dirs
   - `Bash(ls /home/)` returns empty or permission denied
   - `Bash(cat /etc/shadow)` fails (file not mounted)
   - Agent cannot reach other projects' DTTP services via HTTP
   - `bubblewrap` fallback works on kernels without user namespace support
