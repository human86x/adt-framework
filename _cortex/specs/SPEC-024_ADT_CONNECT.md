# SPEC-024: ADT Connect (Secure Remote Access)

**Status:** DRAFT
**Priority:** MEDIUM
**Owner:** Systems_Architect (spec), DevOps_Engineer (implementation)
**Created:** 2026-02-12
**References:** SPEC-015 (Operational Center), SPEC-021 (Operator Console)

---

## 1. Purpose

Provide a simple, zero-config way to expose the ADT Operational Center and Operator Console over the internet without requiring a VPS, static IP, or port forwarding. This allows users to test the framework on remote hosts or share their governance dashboard with collaborators securely.

---

## 2. Technical Strategy: Cloudflare Tunnels

We will utilize **Cloudflare Tunnel** (`cloudflared`) as the underlying transport. It creates a secure outbound-only connection to Cloudflare's edge, bypassing NAT and firewalls while providing an encrypted HTTPS URL.

### 2.1 Benefits
- **No VPS required:** Works from behind home/office routers.
- **Security:** No open inbound ports on the host machine.
- **Free:** Cloudflare Tunnels are free to use.
- **Professional:** Provides stable `*.trycloudflare.com` URLs or custom domains.

---

## 3. The `adt connect` Command

We will implement a new CLI command in the ADT SDK/CLI to manage remote access.

### 3.1 `adt connect share`
1.  **Check Dependency:** Check if `cloudflared` is in the PATH. If not, offer to download the portable binary for the current OS.
2.  **Start Tunnel:** Launch `cloudflared tunnel --url http://localhost:5000` (Panel) and optionally another for the Console/PTY port if needed.
3.  **URL Broadcast:** Capture the generated `*.trycloudflare.com` URL from stdout.
4.  **Display:** Present the URL to the user in a prominent box.
5.  **ADS Log:** Log the start of a remote sharing session to ADS for audit.

---

## 4. Console Integration

The **ADT Operator Console** will have a "Go Remote" toggle in the status bar.

1.  **Activation:** Clicking the toggle triggers the `adt connect share` logic.
2.  **URL Sharing:** The public URL is copied to the clipboard.
3.  **Remote Identity:** The console UI displays a "REMOTE SESSION ACTIVE" badge.

---

## 5. Security Constraints

### 5.1 Access Control
By default, the tunnel URL is public. For production-ready remote access, we must implement:
- **Authentication:** The ADT Panel should require a shared secret or token (defined in `config/dttp.json`) when accessed from a non-localhost IP.
- **Session Limiting:** Tunnels should be ephemeral by default and expire after a configurable duration.

### 5.2 Jurisdiction Guard
The DTTP gateway will log the source IP of all requests. Remote requests will be flagged in the ADS for higher scrutiny by the Overseer.

---

## 6. Implementation Tasks

| Task | Description | Assigned To |
|------|-------------|-------------|
| **task_046** | Implement `adt connect share` in `adt_sdk/cli.py`. | Backend_Engineer |
| **task_047** | Add "Remote Access" UI toggle and status display to the Console. | Frontend_Engineer |
| **task_048** | Implement basic Token-based Auth for ADT Panel remote access. | Backend_Engineer |

---

## 7. Acceptance Criteria

- [ ] User can run `adt connect share` and receive a working HTTPS URL.
- [ ] The ADT Panel is fully functional over the tunnel.
- [ ] Closing the CLI command or toggling the UI switch terminates the tunnel immediately.
- [ ] Remote sessions are logged to the ADS with the public URL.

---

*"Governance without borders."*