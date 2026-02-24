# SPEC-030: Overseer Operational Authorization

**Status:** APPROVED
**Priority:** HIGH
**Owner:** Systems_Architect
**Created:** 2026-02-15
**References:** AI_PROTOCOL.md, SPEC-020, REQ-015

---

## 1. Purpose

The `Overseer` role is mandated to manage the Authoritative Data Source (ADS), ensure compliance, and perform audits. However, current specifications do not explicitly authorize the `Overseer` role for the actions required to fulfill these duties (e.g., healing the ADS, updating audit documentation, managing work logs).

This spec formally authorizes the `Overseer` role for `edit`, `patch`, and `create` actions on its jurisdictional paths.

---

## 2. Authorized Jurisdictions

The `Overseer` role is authorized to perform `edit`, `patch`, and `create` actions on the following paths:

| Path | Contents |
|------|----------|
| `_cortex/ads/` | Authoritative Data Source events and healing backups |
| `_cortex/docs/` | Overseer audit procedures and compliance documentation |
| `_cortex/requests.md` | Cross-role request tracking |
| `_cortex/work_logs/` | Agent session work logs |

---

## 3. Implementation Plan

### 3.1 Spec Registration (Systems_Architect)
- Register `SPEC-030` in `config/specs.json`.
- Add `Overseer` role and its authorized actions/paths to `SPEC-030` entry.

### 3.2 Jurisdiction Update (Systems_Architect)
- Ensure `config/jurisdictions.json` correctly reflects the `Overseer` role's jurisdiction.

---

## 4. Acceptance Criteria

- [ ] `Overseer` role can successfully submit DTTP requests for `patch` on `_cortex/requests.md`.
- [ ] `Overseer` role can successfully submit DTTP requests for `edit` on `_cortex/ads/` (for healing).
- [ ] All `Overseer` actions are logged to ADS under `SPEC-030`.

---

*"Audit is the backbone of trust. Authorization is the backbone of audit."*
