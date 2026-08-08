"""SPEC-081 §10 -- acceptance tests for project knowledge reuse.

Covers fingerprint determinism, Jaccard similarity behaviour on
domain-related vs. unrelated wishes, combined-score tie-break by
recency, and idempotency of the backfill script.

Runs standalone (no adt-center required).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from adt_core.reuse.fingerprint import (  # noqa: E402
    combined_score,
    compute_fingerprint,
    recency_weight,
    similarity,
)


SOLAR_WISH_A = (
    "A browser 3D solar system with hand tracking webcam camera pan. "
    "Sun centre, planets orbit log distances, clicking planet opens "
    "fact card real distance diameter."
)

SOLAR_WISH_B = (
    "Browser 3D solar system hand tracking webcam camera pan. "
    "Sun centre, planets orbit log distances, click planet opens "
    "fact card real distance diameter."
)

POMODORO_WISH = (
    "A minimalist pomodoro timer that runs in the terminal. 25-minute "
    "work intervals alternating with 5-minute breaks. Displays a large "
    "digit countdown and plays a chime when each interval ends."
)


def test_fingerprint_deterministic():
    """Same wish, computed twice, yields the same hash + token list."""
    fp1 = compute_fingerprint(SOLAR_WISH_A)
    fp2 = compute_fingerprint(SOLAR_WISH_A)
    assert fp1["hash"] == fp2["hash"]
    assert fp1["tokens"] == fp2["tokens"]
    # Different input -> different hash.
    fp3 = compute_fingerprint(POMODORO_WISH)
    assert fp3["hash"] != fp1["hash"]


def test_similarity_solar_vs_solar_gt_0_7():
    """Two solar-system wishes must show Jaccard similarity >= 0.70."""
    fp_a = compute_fingerprint(SOLAR_WISH_A)
    fp_b = compute_fingerprint(SOLAR_WISH_B)
    sim = similarity(fp_a, fp_b)
    assert sim >= 0.70, f"expected >=0.70, got {sim}"


def test_similarity_solar_vs_pomodoro_lt_0_3():
    """Unrelated wishes must show Jaccard similarity < 0.30."""
    fp_solar = compute_fingerprint(SOLAR_WISH_A)
    fp_pom = compute_fingerprint(POMODORO_WISH)
    sim = similarity(fp_solar, fp_pom)
    assert sim < 0.30, f"expected <0.30, got {sim}"


def test_combined_score_recency_wins_ties():
    """With near-equal similarity, the more-recently-touched wins."""
    now = datetime.now(timezone.utc)
    recent_iso = now.isoformat().replace("+00:00", "Z")
    stale_iso = (now - timedelta(days=45)).isoformat().replace("+00:00", "Z")

    # Fixed similarity value; both projects would match equally well.
    sim = 0.75

    recent_score = combined_score(sim, recency_weight(recent_iso))
    stale_score = combined_score(sim, recency_weight(stale_iso))

    assert recent_score > stale_score, (
        f"recent {recent_score} should beat stale {stale_score}"
    )


def test_backfill_idempotent(tmp_path, monkeypatch):
    """Running backfill twice must leave the output line count unchanged."""
    # Build a synthetic Projects tree with two forge_brief.json files.
    projects_root = tmp_path / "Projects"
    projects_root.mkdir()

    for pname, wish in (
        ("solar_test_1", SOLAR_WISH_A),
        ("pomodoro_test_1", POMODORO_WISH),
    ):
        proj = projects_root / pname
        (proj / "_cortex" / "ops").mkdir(parents=True)
        (proj / "_cortex" / "specs").mkdir(parents=True)
        brief = {
            "intent_description": wish,
            "name": pname,
            "path": str(proj),
        }
        (proj / "_cortex" / "ops" / "forge_brief.json").write_text(
            json.dumps(brief)
        )

    # Isolated fingerprint output under tmp_path.
    fp_path = tmp_path / "project_fingerprints.jsonl"

    # Import the backfill module and monkey-patch its module-level
    # constants to point at the temp tree.
    import importlib.util

    script_path = os.path.join(
        _REPO_ROOT, "_cortex", "ops", "backfill_fingerprints.py"
    )
    spec = importlib.util.spec_from_file_location(
        "backfill_fingerprints_test", script_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "PROJECTS_ROOT", str(projects_root))
    monkeypatch.setattr(module, "FINGERPRINTS_PATH", str(fp_path))

    # First run -> two lines.
    rc1 = module.main()
    assert rc1 == 0
    with open(fp_path, "r", encoding="utf-8") as f:
        lines1 = [ln for ln in f.read().splitlines() if ln.strip()]
    assert len(lines1) == 2

    # Second run -> still two lines (idempotent).
    rc2 = module.main()
    assert rc2 == 0
    with open(fp_path, "r", encoding="utf-8") as f:
        lines2 = [ln for ln in f.read().splitlines() if ln.strip()]
    assert len(lines2) == 2, (
        f"expected 2 lines after second run, got {len(lines2)}"
    )
