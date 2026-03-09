# Work Log — 2026-03-03 (Backend_Engineer)

**Session:** REQ-038 & REQ-039 Remediation
**Agent:** GEMINI
**Role:** Backend_Engineer
**Spec:** SPEC-017 / SPEC-020

## Summary

Implemented fixes for REQ-038 and REQ-039 to address permission issues in ADS healing and inconsistent role/agent casing in DTTP logging. Verified sandbox PYTHONPATH requirements for REQ-028.

## Actions Taken

1. **REQ-038 (ADS Healer Fix):**
   - Modified adt_core/ads/healer.py to use shutil.copy instead of shutil.copy2.
   - Reason: Avoid PermissionError when attempting to copy metadata (copystat) in the hardened _cortex/ads/ directory.
   - Verification: Ran healer.py on a temporary file, confirmed backup creation and no errors.

2. **REQ-039 (ADS Normalization):**
   - Updated adt_core/dttp/service.py (/log endpoint) to import ADSEventSchema and call normalize_role() and normalize_agent() on incoming data before logging.
   - Reason: SPEC-020 Amendment B requires canonical casing in the ADS to ensure hash stability.
   - Verification: Simulated /log request with agent: 'gemini' and role: 'overseer', confirmed ADS recorded GEMINI and Overseer.

3. **REQ-028 (Sandbox Verification):**
   - Verified that PYTHONPATH=/home/human/Projects/adt-framework allows successful import of adt_sdk.client in a system-python environment.
   - Recommendation: PTY spawner should also add the framework's venv site-packages to PYTHONPATH to ensure third-party dependencies like requests are available if not in the system path.

4. **DTTP Service Recovery:**
   - Identified that DTTP services were in a stopped (T) state. Requested human intervention to clear and restart services.
   - Successfully used dttp_request.py (via shell) to perform a Tier 2 patch on service.py after role/spec switching.

## Status

- REQ-038: COMPLETED
- REQ-039: COMPLETED
- REQ-028: VERIFIED (Response provided to DevOps_Engineer)

All core backend tasks from tasks.json remain completed. No regressions observed in existing test suite (46 passed).
