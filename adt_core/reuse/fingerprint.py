"""SPEC-081 §2 -- project fingerprinting utilities.

Cheap, deterministic keyword fingerprint over a project's wish text.
Used to find "have we already forged something like this?" without any
model call. Jaccard similarity over normalised token sets + exponential
recency decay produces a combined score that ranks past projects for the
Forge Wizard's reuse picker.

Pure-Python; stdlib only. Safe to import at process startup.
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone
from typing import Dict, Iterable, List


# Small stop-word set. Deliberately tiny -- the goal is to strip
# structural glue words while keeping domain vocabulary intact.
STOPWORDS = {
    "a", "the", "and", "or", "of", "to", "in", "for", "with", "an",
}


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    """Lowercase, split into alphanumeric tokens, drop stopwords, dedupe.

    Sorted output makes the token list itself hashable in a stable way.
    """
    if not text:
        return []
    lowered = text.lower()
    raw = _TOKEN_RE.findall(lowered)
    uniq = {t for t in raw if t and t not in STOPWORDS}
    return sorted(uniq)


def compute_fingerprint(wish_text: str) -> Dict[str, object]:
    """Return ``{"tokens": [...sorted unique...], "hash": "sha256..."}``.

    ``hash`` is over the joined token list so two identical wishes yield
    the same hash regardless of insertion order.
    """
    tokens = _tokenize(wish_text or "")
    joined = " ".join(tokens)
    h = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return {"tokens": tokens, "hash": h}


def similarity(fp_a: Dict[str, object], fp_b: Dict[str, object]) -> float:
    """Jaccard similarity between two fingerprints' token sets.

    Empty on both sides -> 0.0 (no basis for comparison).
    """
    a = set(fp_a.get("tokens") or [])
    b = set(fp_b.get("tokens") or [])
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return inter / union


def recency_weight(last_touched_iso: str) -> float:
    """Return ``exp(-days_since_last_touched / 30)`` in [0, 1].

    30-day timescale means a project touched today weighs ~1.0 and one
    touched 30 days ago weighs ~0.37. Anything unparseable -> 0.0.
    """
    if not last_touched_iso:
        return 0.0
    try:
        # Accept both Z-suffix and +HH:MM offsets.
        iso = last_touched_iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return 0.0
    now = datetime.now(timezone.utc)
    days_since = max(0.0, (now - dt).total_seconds() / 86400.0)
    return math.exp(-days_since / 30.0)


def combined_score(similarity_value: float, recency_weight_value: float) -> float:
    """Weighted combination -- 60% content similarity, 40% recency.

    Per SPEC-081 §3 the picker prefers the more recent of two similarly
    matching prior projects.
    """
    s = max(0.0, min(1.0, similarity_value or 0.0))
    r = max(0.0, min(1.0, recency_weight_value or 0.0))
    return 0.6 * s + 0.4 * r


__all__ = [
    "STOPWORDS",
    "compute_fingerprint",
    "similarity",
    "recency_weight",
    "combined_score",
]
