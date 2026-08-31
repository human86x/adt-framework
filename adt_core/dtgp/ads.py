"""ADS logging helper for DTGP.

Emits events via POST http://localhost:5002/log (DTCP service endpoint).
Falls back to direct file append if DTCP is unavailable.

All description strings MUST be ASCII-safe (project memory: UTF-8 crashes
the backwards-seeking reader in adt_core/ads/logger.py).

SPEC-113.
"""
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

DTCP_LOG_URL = "http://localhost:5002/log"
_SESSION_ID: str = ""
_ADS_PATH: str = ""


def configure(session_id: str, ads_path: str = ""):
    global _SESSION_ID, _ADS_PATH
    _SESSION_ID = session_id
    _ADS_PATH = ads_path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _gen_id(action_type: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
    return f"evt_{ts}_{action_type[:15]}"


def log_event(
    action_type: str,
    description: str,
    action_data: Optional[dict] = None,
    tier: int = 3,
) -> str:
    """Emit a single ADS event. Returns the event_id."""
    event_id = _gen_id(action_type)
    payload: dict[str, Any] = {
        "event_id": event_id,
        "ts": _now_iso(),
        "agent": "CLAUDE",
        "role": "Backend_Engineer",
        "action_type": action_type,
        "description": description,
        "spec_ref": "SPEC-113",
        "authorized": True,
        "tier": tier,
        "session_id": _SESSION_ID,
        "parent_session_id": "sess_arch_20260829_121818_claude",
    }
    if action_data:
        data = dict(action_data)
        data["authority"] = "operator_sovereign_override_for_SPEC-113"
        payload["action_data"] = data
    else:
        payload["action_data"] = {
            "authority": "operator_sovereign_override_for_SPEC-113"
        }

    # Try DTCP log endpoint first
    try:
        resp = requests.post(DTCP_LOG_URL, json=payload, timeout=3)
        if resp.ok:
            return event_id
    except Exception as exc:
        logger.debug("DTCP log endpoint unavailable (%s), falling back to file", exc)

    # Fallback: direct append to ADS file
    if _ADS_PATH and os.path.exists(os.path.dirname(_ADS_PATH)):
        try:
            with open(_ADS_PATH, "a", encoding="ascii", errors="replace") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception as exc2:
            logger.warning("ADS fallback write failed: %s", exc2)

    return event_id
