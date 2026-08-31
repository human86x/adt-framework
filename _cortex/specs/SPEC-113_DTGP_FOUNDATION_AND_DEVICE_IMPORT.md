# SPEC-113 — DTGP Foundation and Device Import

**Status:** APPROVED
**Author:** Systems_Architect (CLAUDE, 2026-08-29)
**Authority:** Operator verbal approval, 2026-08-29 (this session — "dtgp - go" for draft, "2" for approve-and-build)
**Category:** Governance Infrastructure
**Relates to:** DTCP (`adt_core/dtcp/`), SPEC-031 (External Project Governance), SPEC-110 (Governed Project Standards Propagation), SPEC-057 (Agent Mailbox), SPEC-112 (candidate — Role Vocabulary Extension), SPEC-114 (planned — Intent Alignment & Consent Gates), SPEC-115 (planned — Embedded_Engineer & Firmware Actions), SPEC-116 (planned — Deployment Action Drivers)

**Intent:** Introduce **DTGP — Digital Transformation Gateway Protocol** — a sibling service to DTCP (Digital Transformation Control Protocol) that mediates every ADT worker action whose effects extend beyond this process's local filesystem: SSH into a remote host, SFTP a build to a server, POST to a webhook, `git push`, flash an Arduino via a Pi over USB. DTGP holds credentials, resolves multi-hop access paths, serialises access per target, and logs every crossing to ADS. It gives operators a governed on-ramp for adding devices and remote targets to a project with their credentials and procedures in one place.

**Triggering Event:** On 2026-08-29 the operator asked whether ADT should have a hardware governance layer, then generalised the question — every deployment from an ADT worker (HTTP, FTP, SSH, git push, firmware flash) crosses the process boundary and today does so with raw agent-held credentials, no serialisation, no audit chain beyond what individual agents remember to log. The concrete driver is OceanPulse: two Arduino Megas, a Pi 3 and a Pi 5, USB decoder boards, LoRa modules — the Arduino is physically connected to a Pi, and any flash from ADT must go **through** the Pi over SSH. Without a mediation layer, an agent gets raw creds, races another agent for the USB port, and has no gate against flashing the wrong device.

**Success Condition:** After this spec ships:
1. A `dtgp` service is running per governed project, on its own allocated port, health endpoint responding.
2. A per-project `_cortex/devices.json` registry exists, populated via a Console wizard or CLI, referencing device-type templates from `_cortex/device_types/`.
3. Credentials for every registered target live in the DTGP vault (out of the project repo, encrypted at rest via OS keyring), referenced from the registry only by `dtgp://creds/<ref>`.
4. An agent can call `dtgp.action(target_id, action, artifact?)` and DTGP resolves the access path — including transit hops — executes the action under a per-device mutex, and emits an ADS event chain capturing every hop and every credential dereference (by ref, not by material).
5. A starter library of common device types (Arduinos, ESP32, Pis, SSH/HTTP/SFTP endpoints, git remotes) ships with the framework and propagates to every governed project via SPEC-110.
6. Adding a device to a project is a Console-wizard action of under a minute for common types.

---

## 1. Positioning

DTCP mediates local file and process operations. DTGP mediates external effects — anything that crosses the machine boundary.

| Dimension | DTCP (existing) | DTGP (this spec) |
|---|---|---|
| Domain | Files and processes on the ADT host | Targets beyond the ADT host |
| Identity primitive | Path | Target ID |
| Authority primitive | Path jurisdiction | Target jurisdiction + credentials |
| Latency | Microseconds | Milliseconds to seconds (network) |
| Failure model | Fast-fail | Timeouts, partial failure, retry |
| Serialisation | Implicit (fs is thread-safe) | Explicit (mutex per target) |
| Reversal | git revert | Depends — some actions are irreversible (webhook fired, firmware flashed) |

DTGP is a sibling service, not an extension of DTCP. Different latency profile, different auth model, different failure semantics. It shares:
- The ADS event ledger (both log to `_cortex/ads/events.jsonl`).
- Role vocabulary (jurisdictions.json).
- SCR mechanism (for Tier-1 targets, planned in SPEC-114).
- Tier concept.

## 2. Scope

### In scope for SPEC-113

- DTGP service scaffold: Flask app, health endpoint, config, per-project port allocation (mirrors the DTCP model).
- Target / Action / Artifact type model.
- Access-path resolution with **transit hops** (target reached through another registered target).
- Device Type Templates — YAML definitions of device classes and their procedures.
- Device Instance registry — `_cortex/devices.json`, per-project.
- Import flow: Console wizard, CLI (`adt device add`), and bulk YAML import.
- Credential vault (out of project repo, encrypted at rest, ref-only access from agents).
- Per-target lock manager with chain-locking rule to prevent deadlock across shared transit hops.
- First three protocol drivers: SSH, USB-serial, HTTP.
- Discovery probe: on service start and on-demand; compares live-detected devices against the registry.
- ADS event types for device lifecycle and action execution.
- Starter library of common device types propagated via SPEC-110.

### Out of scope for SPEC-113 (deferred to follow-on specs)

- **Intent alignment** (task-binding, artifact manifests, wrong-device / wrong-artifact refusal) — **SPEC-114**.
- **Human consent (hardware SCR) flow** for Tier-1 targets — **SPEC-114**.
- **Embedded_Engineer role** and the four-stage physical-safety flash gate — **SPEC-115**.
- **SFTP, git push, S3 put, kubectl, docker push** drivers — **SPEC-116**.
- **Cross-project device sharing** (one Pi used by two projects).
- **Device-to-device orchestration** (device A talks to device B as part of a test) — future spec.
- **Vault backing by HSM or cloud KMS** — v1 uses OS keyring or operator-supplied key.
- **Credential rotation UI / automation** — v1 provides the CLI primitive, no scheduler.

## 3. Design

### 3.1 Service Scaffold

- Location: `adt_core/dtgp/` (mirrors `adt_core/dtcp/`).
- Framework: Flask (matches DTCP for operational consistency).
- Port allocation: per-project, same allocator DTCP uses. Recorded in the project registry entry alongside `dtcp_port`.
- Config: `~/.adt-dtgp/config.yaml` for host-level settings (vault path, keyring backend); `_cortex/dtgp/config.yaml` for per-project overrides.
- Startup: launched by adt-center alongside DTCP when a project becomes active.
- Health: `GET /health` returns `{status, version, uptime, active_locks_count, vault_status}`.

### 3.2 Target / Action / Artifact Model

Three primitives compose every governed egress operation.

**Target** — anything addressable outside the process. Identified by a stable `target_id`. Types: device, ssh_host, http_endpoint, sftp_server, git_remote, s3_bucket, etc.

**Action** — a verb performed on a target. Declared by the target's type. Examples: `ssh_exec`, `flash`, `http_post`, `sftp_upload`, `git_push`. Each action declares which gate set applies (SPEC-114 layers gate composition on top).

**Artifact** (optional) — payload where one exists: firmware file, HTTP body, tarball. Carries a manifest (SPEC-114) declaring compatibility. In SPEC-113 the artifact is passed as a file path or inline bytes; manifest enforcement is deferred.

Every real operation is the tuple `(action, target_id, artifact?, task_context?)`. DTGP receives it via a single unified endpoint, walks the gate chain, executes.

### 3.3 Access-Path Resolution

Every target's registry entry carries an ordered `access_path` — the chain of hops that gets you to the endpoint. The last hop is where the action executes; every earlier hop is a **transit target** that must itself be registered.

Example (Arduino reached via a Pi):

```json
{
  "arduino_mega_lora_gw_01": {
    "type": "arduino_mega_2560",
    "serial": "754323034393518011E1",
    "tier": 2,
    "jurisdiction": ["Embedded_Engineer"],
    "environment": "lab",
    "access_path": [
      {"hop": "pi_gateway_01", "protocol": "ssh", "credentials_ref": "dtgp://creds/pi_gateway_01_ssh"},
      {"hop": "local", "protocol": "usb_serial", "port_symlink": "/dev/ttyUSB_arduino_gw"}
    ]
  }
}
```

Resolution algorithm:
1. Load target's `access_path`.
2. For every `hop` that names another `target_id`, recursively resolve that target's path — the transit chain expands into a fully-flattened `[connection, connection, ...]` sequence.
3. Validate jurisdiction on every hop, not just the terminal target.
4. Acquire locks on every hop in **lexicographic order of target_id** (rule: prevents deadlock when two operations share transit devices).
5. Establish connections hop-by-hop. First hop uses local machine. Each subsequent hop tunnels through the previous.
6. Execute the action at the terminal hop.
7. Tear down connections in reverse order. Release locks in reverse order.

Physical port pinning: `port_symlink` MUST be a udev symlink (e.g. `/dev/ttyUSB_arduino_gw`), not a bare `/dev/ttyUSB0` — port numbers shift on reboot. The starter library includes a udev-rule generator per template.

### 3.4 Device Type Templates

Location: `_cortex/device_types/*.yaml` (per-project). Starter library ships under the framework's `_cortex/standards/device_types/ADT_*.yaml` and propagates to every project via SPEC-110.

A template declares what a class of devices IS: capabilities, how to identify one, and the procedures for every action DTGP can perform on it. Templates NEVER contain credentials or project-specific values.

```yaml
# _cortex/device_types/arduino_mega_2560.yaml
id: arduino_mega_2560
name: Arduino Mega 2560
capabilities: [usb_serial, flash, gpio]
identification:
  usb_vid: "2341"
  usb_pid: "0042"
  discovery_hint: "avrdude -c wiring -p atmega2560 -P {port} -v 2>&1 | grep 'Device signature'"
  udev_rule: 'SUBSYSTEM=="tty", ATTRS{idVendor}=="2341", ATTRS{idProduct}=="0042", ATTRS{serial}=="{serial}", SYMLINK+="ttyUSB_{alias}"'
procedures:
  flash:
    tool: avrdude
    args: "-c wiring -p atmega2560 -P {port} -b 115200 -U flash:w:{artifact}:i"
    verify: "avrdude -c wiring -p atmega2560 -P {port} -U flash:v:{artifact}:i"
  backup:
    tool: avrdude
    args: "-c wiring -p atmega2560 -P {port} -U flash:r:{out_path}:i"
    default_out_path: "_cortex/firmware_snapshots/{target_id}_{ts}.hex"
  health:
    protocol: serial
    baudrate: 115200
    probe: "PING\n"
    expect: "PONG\n"
    timeout_ms: 2000
  reset:
    tool: stty
    args: "-F {port} hupcl"
safety_notes:
  - "Bootloader can be corrupted by wrong programmer setting."
  - "Undervoltage during flash produces silent partial writes."
```

Starter library minimum for v1:
- `arduino_mega_2560`
- `arduino_uno`
- `esp32_devkit`
- `raspberry_pi_5`
- `raspberry_pi_3b`
- `ssh_linux_host`
- `http_endpoint`

Every starter template file is named `ADT_<TYPE>.yaml` in the framework repo so SPEC-110's propagation regex (`ADT_*.md` extended to `ADT_*.yaml`) picks them up. In-project templates use unprefixed names.

### 3.5 Device Instance Registry

Location: `_cortex/devices.json` (per-project). Tier 3 (operator-editable, no SCR). Written only by DTGP endpoints; hand-edit is discouraged but tolerated.

Every entry:
- References a `type` (device-type template ID).
- Adds instance data: serial, hostname, port_symlink, location, environment, tier, jurisdiction.
- Declares its `access_path` (may reference other targets by ID).
- May override any inherited procedure locally (rare — for the weird device with a bad clock crystal).

### 3.6 Credential Vault

Location: `~/.adt-dtgp/vault/<project_id>/<ref>.enc` (per-host, per-project, gitignored — never in the repo).

Encryption:
- At-rest via OS keyring (Linux: SecretService/keyring; macOS: Keychain; Windows: Credential Manager).
- Fallback: operator-supplied master key stored in `~/.adt-dtgp/master.key` with `chmod 600`; DTGP refuses to start if fallback is chosen and file is world-readable.

API contract:
- `POST /credentials` — write. Body: `{ref, material, project_id}`. Response: `{ref, created_at}`. Rate-limited.
- `PUT /credentials/{ref}` — rotate. Body: `{material}`. Response: `{ref, rotated_at, previous_hash}`.
- `DELETE /credentials/{ref}` — revoke. Response: `{ref, revoked_at}`.
- **NO `GET /credentials/{ref}` exists.** Credentials leave the vault only during action execution, held in the driver's local stack frame, zeroed after use.

Agents never see credential material. They pass `credentials_ref` values around and DTGP dereferences internally.

### 3.7 Lock Manager

Purpose: prevent concurrent operations on the same physical resource.

- Per-target mutex, keyed by `target_id`.
- Chain-locking rule: for an operation whose access_path expands to targets `[A, B, C]`, acquire locks in **lexicographic order of target_id** across the expanded chain. Not path order — cross-operation deadlock prevention requires a globally consistent order.
- Configurable per-action lock timeout. Default 30s wait, then fail with `LockTimeout`.
- Locks are process-local to DTGP (single-node v1). Persistent lock records via ADS event so a crashed DTGP leaves an audit trail; recovery clears stale locks on next start.
- API for observability: `GET /locks` returns current holders + waiters.

### 3.8 ADS Event Types

Add to `adt_core/ads/schema.py`:

```
DTGP_EVENTS = [
    "device_type_registered",      # {type_id, source: starter|project|import}
    "device_registered",           # {target_id, type, jurisdiction, tier, environment}
    "device_updated",              # {target_id, changed_keys[]}
    "device_removed",              # {target_id}
    "device_discovered",           # {target_id, match: true, serial_matched, protocol}
    "device_missing",              # {target_id, last_seen_at, reason}
    "device_serial_mismatch",      # {target_id, expected, actual, severity}
    "credential_stored",           # {ref, project_id, target_hint} — NEVER material
    "credential_rotated",          # {ref, previous_hash, rotated_at}
    "credential_revoked",          # {ref, revoked_at}
    "dtgp_action_requested",       # {target_id, action, artifact_ref, requester_role, requester_session}
    "dtgp_action_denied",          # {target_id, action, reason} — jurisdiction, lock timeout, target missing
    "dtgp_action_started",         # {target_id, action, expanded_chain, locks_acquired}
    "dtgp_action_completed",       # {target_id, action, outcome, duration_ms}
    "dtgp_action_failed",          # {target_id, action, reason, hop_that_failed}
    "dtgp_lock_acquired",          # {target_id, holder, wait_ms}
    "dtgp_lock_released",          # {target_id, holder, held_ms}
    "dtgp_lock_timeout",           # {target_id, requester, waited_ms}
]
```

Every event includes standard schema fields plus DTGP-specific ones. Descriptions ASCII-safe per project convention.

### 3.9 Protocol Drivers (v1 set)

Each driver implements the same interface:
- `connect(hop_config, upstream_conn?) -> connection`
- `execute(connection, action_spec, artifact?) -> result`
- `probe(hop_config) -> probe_result`
- `disconnect(connection)`

Drivers shipped in v1:

- **ssh** — Paramiko-based. Supports jump-through-upstream when `upstream_conn` provided. Auth via key from vault ref. Timeouts configurable.
- **usb_serial** — pyserial-based. Only usable as terminal hop (no tunnelling through a serial line). Enforces `port_symlink`, refuses raw `/dev/ttyUSB<N>`. Supports read/write and command-execution patterns (for `avrdude` invocation on the transit host).
- **http** — httpx-based. Supports GET/POST/PUT/DELETE, auth headers from vault ref, TLS verification on by default.

Additional drivers (SFTP, FTP, git-push, S3, kubectl) land in **SPEC-116**.

## 4. Task Breakdown

- task_1: Service scaffold (`adt_core/dtgp/` — app, config, health, port allocator integration with adt-center). **Role:** Backend_Engineer.
- task_2: Device Type Template loader + validator. Draft the starter library YAMLs (7 types). **Role:** Backend_Engineer + Systems_Architect (Architect owns the YAML content in `_cortex/standards/device_types/ADT_*.yaml`).
- task_3: Device Instance registry — JSON schema, load/save, CRUD endpoints (`/devices`, `/devices/{id}`, POST for register, PUT for update, DELETE for remove). **Role:** Backend_Engineer.
- task_4: Credential vault — filesystem layout, OS-keyring integration, POST/PUT/DELETE endpoints, refusal of GET. **Role:** Backend_Engineer.
- task_5: Access-path resolver + lock manager (chain lock, lexicographic order, timeout). **Role:** Backend_Engineer.
- task_6: Protocol driver framework + SSH/USB-serial/HTTP drivers. **Role:** Backend_Engineer.
- task_7: Register DTGP_EVENTS in `adt_core/ads/schema.py`, emit them from every mutating path. **Role:** Backend_Engineer.
- task_8: Discovery probe — on service start and on-demand endpoint, uses template identification hints. **Role:** Backend_Engineer.
- task_9: Console "Add Device" wizard. Template picker, instance form, credential entry (never displayed), inline discovery probe. **Role:** Frontend_Engineer.
- task_10: Console device list + detail view with health indicator and current-lock state. **Role:** Frontend_Engineer.
- task_11: CLI `adt device add|list|remove|probe|rotate-credentials` commands. **Role:** DevOps_Engineer.
- task_12: End-to-end verification. Register two devices (one reached via transit), run a probe, execute a mocked action, confirm ADS chain and lock behaviour. **Role:** DevOps_Engineer.

## 5. Acceptance Criteria

- `curl http://localhost:<dtgp_port>/health` returns `{status: "ok", ...}` after adt-center starts a project.
- Starter library ships at least 7 device-type YAMLs in `_cortex/standards/device_types/ADT_*.yaml` in the framework repo.
- Console wizard adds a device in under a minute for a starter-library type; entry appears in `_cortex/devices.json` with a `credentials_ref` (not raw material).
- `cat _cortex/devices.json | jq '.[] | .access_path[].credentials_ref'` shows only `dtgp://creds/...` strings — never a plaintext key.
- `curl http://localhost:<dtgp_port>/credentials/<ref>` returns 404 or method-not-allowed (no read endpoint exists).
- Two concurrent action requests on the same target serialise via the lock manager; ADS shows one `dtgp_lock_acquired` then a wait, then the second `dtgp_lock_acquired` after the first releases.
- An action against a target with a transit hop resolves the chain, acquires locks on both, executes, releases. ADS event `dtgp_action_started` shows `expanded_chain: [transit_id, target_id]`.
- Discovery probe against a connected device with a matching template returns `match: true` and emits `device_discovered`.
- Removing a device via the CLI emits `device_removed` and cleanly nulls its `credentials_ref` from the registry (credential material itself deleted from the vault).
- Docs updated: `adt-console/src/index.html` about page references DTGP alongside DTCP.

## 6. Non-Goals

- Firmware flash gates and the four-stage physical-safety flow — SPEC-115.
- Intent-alignment gates (task-binding, artifact manifests, wrong-device refusal) — SPEC-114.
- Human consent SCR for Tier-1 targets — SPEC-114.
- Additional protocol drivers (SFTP, FTP, git push, S3, kubectl, docker) — SPEC-116.
- Cross-project device sharing.
- Device-to-device flows (Pi initiates action on Arduino as part of a test).
- HSM / cloud-KMS backing for the vault.
- Automated credential rotation scheduler.
- Multi-node DTGP (v1 is single-node per project).

## 7. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Vault compromise if operator machine is breached. | OS keyring encryption, `chmod 600` on fallback key file, per-project vault directories, ADS event on every store/rotate/revoke for audit. Vault directory outside project repo so it doesn't leak via git or backups by default. |
| Lock manager deadlock across chained transit devices. | Lexicographic lock ordering by `target_id` across the full expanded chain. Timeout with fail-fast so a stuck lock is always eventually broken. |
| Discovery false positives (two identical Arduinos on the bus). | Discovery matches by SERIAL, not just VID/PID. Template's `identification.udev_rule` uses serial to build the port symlink. |
| Credential loss if vault file lost. | Vault is per-host; operator responsibility for backup. Document this in the wizard's first-use flow. Every credential also has an ADS `credential_stored` audit event so the operator knows what needs re-provisioning. |
| Protocol driver bugs cause DTGP to hang. | Every driver call is wrapped in a timeout; timeouts are ADS-logged as `dtgp_action_failed` with `reason: driver_timeout`. |
| Agents route around DTGP by calling `ssh`/`avrdude`/`curl` directly. | Enforcement is by convention in v1 — no OS-level block. The DTCP pretool hook is extended in a follow-on to detect direct calls to known bypassable tools and warn. Full enforcement (nsjail-style outbound denial) is a v2 concern once the concept proves itself. |
| Wizard collects a credential and DTGP crashes before persisting. | Wizard reflects `credential_stored` ADS event before proceeding. Failure at persist step aborts the wizard cleanly and instructs re-entry. |

## 8. Dependencies

- **DTCP** (`adt_core/dtcp/`) — DTGP borrows its Flask scaffold, port allocation approach, and hook-integration pattern.
- **SPEC-110** — Standards Propagation, for shipping the starter device-type library to every project as `_cortex/standards/device_types/ADT_*.yaml`.
- **SPEC-057** — Agent Mailbox, potentially useful for cross-role coordination during action execution; not strictly required for v1.
- **`_cortex/jurisdictions.json`** — source of truth for role names used in device jurisdiction fields.
- **adt-center project registry** — DTGP port allocation and lifecycle piggyback on the same per-project pattern DTCP already uses.

## 9. Follow-On Work (Not This Spec)

- **SPEC-112** — Role Vocabulary Extension. Adds `Embedded_Engineer` and other project-specific roles. Precondition for SPEC-115.
- **SPEC-114** — Intent Alignment and Consent Gates. Task-binding, artifact manifests, hardware SCR flow for Tier-1 targets. Layers on top of SPEC-113's action model.
- **SPEC-115** — Embedded_Engineer Role and Firmware Actions. Four-stage physical-safety flash gate (presence, backup, consent, verify) with rollback from snapshot. Depends on SPEC-112 + SPEC-113 + SPEC-114.
- **SPEC-116** — Deployment Action Drivers. SFTP, FTP, git push, S3 put, kubectl, docker push, cloud provider SDKs. Depends on SPEC-113 driver framework.

## 10. Rollout

1. **task_1** service scaffold — lands independently, exposes `/health` only. Verifies port allocation and startup path.
2. **task_2 + task_3 + task_4** — templates, registry, vault, together on one branch. Verifies data plane before any real action can happen.
3. **task_5 + task_6** — resolver, lock manager, drivers. Verifies control plane and can execute actions.
4. **task_7 + task_8** — ADS events wired throughout, discovery probe live. Verifies observability and safety net.
5. **task_9 + task_10** — Console UI (wizard + list). Verifies operator surface.
6. **task_11** — CLI. Verifies scripted usage.
7. **task_12** — end-to-end verification with a real device (Arduino via Pi over SSH) and a mocked HTTP endpoint.
8. Update `MASTER_PLAN.md` to add SPEC-113 as ACTIVE (via SCR — MASTER_PLAN is Tier 1).

---

*"Governance stops at the process boundary only if we let it. DTGP extends the boundary."*
