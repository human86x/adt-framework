"""REQ-111: MRR / intent-matcher expansion tests.

Covers:
  1. Solar-system wish (SPEC-079) hits the expected multi-domain set.
  2. AR-art wish (SPEC-077) hits AR + web_camera at minimum.
  3. Empty wish still returns a valid detail dict (needed so the caller can
     still emit intent_match_completed with empty payload).
  4. REQ-111 acceptance: a total no-match wish still returns a well-formed
     detail dict, so the calling code always has data to emit for the
     completed event.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from adt_core.standards.intent_matcher import (  # noqa: E402
    match_intent_domain,
    match_intent_domain_detailed,
    ENGINE_VERSION,
)


# --- SPEC-079 §1 payload (paraphrased below into a single string, as delivered to the matcher) ---
SOLAR_SYSTEM_WISH = (
    "A browser-based educational 3D visualisation of our solar system that runs "
    "entirely offline. The Sun sits at the centre, the 8 major planets orbit at "
    "log-compressed but visually pleasing distances, and Earth's Moon orbits Earth. "
    "Each planet uses a bundled high-resolution equirectangular texture. Planets "
    "rotate on their axes and orbit the Sun at reasonable relative speeds -- not "
    "physically accurate to true Kepler mechanics but faithful to relative ordering. "
    "Navigation is by webcam-tracked hand movement, the same pattern as the EyeToy "
    "template already in this catalog. The user waves or moves their hand in front "
    "of the built-in laptop webcam and the camera pans smoothly through space -- "
    "move hand left, camera pans left; move hand up, camera pitches up. A soft "
    "on-screen indicator shows where the hand is being tracked. No keyboard, no "
    "mouse required for navigation; a mouse click is only needed for planet "
    "selection. Clicking any planet triggers a smooth cinematic fly-to camera "
    "transition (~2 seconds) that frames the planet, then opens a fact card "
    "displaying real-world data. The catalog of facts is a hardcoded JSON file "
    "bundled with the app -- no NASA API calls, no external dependencies at "
    "runtime, works entirely offline. Rendering: Three.js. Camera navigation: "
    "MediaPipe Hands via getUserMedia. Textures: bundled equirectangular JPGs. "
    "Aligns with WCAG 2.2 for accessibility, IAU planetary nomenclature, Khronos "
    "glTF 2.0 conventions, Khronos WebGL 2.0, W3C Media Capture and Streams, "
    "Web Vitals performance budgets, GDPR-compliant camera-consent copy, NGSS / "
    "UNESCO ICT-Competency-Framework, OSI-approved licence (MIT) with SPDX "
    "identifier, JSON Schema (RFC 8259) for planet_facts.json validation, "
    "Unicode UTF-8, Dublin Core educational metadata. Students, educators, "
    "curious learners, families, and museum-style installations."
)


# --- SPEC-077 §1 payload (single-string form) ---
AR_ART_WISH = (
    "A mobile-first web app that lets people preview art pieces (paintings, framed "
    "prints, vases, statuettes) in their own home before buying. The user prints a "
    "paper fiducial marker provided by the app, places it on a wall or shelf where "
    "a piece would go, and points their phone camera at the marker. The app renders "
    "the digitised art piece anchored to the marker at correct real-world scale. "
    "Tracking must be robust and stable. The marker is designed to be detected from "
    "a distance and at varied angles (a multi-fiducial board or natural-feature-"
    "tracking target). Once the marker is initially locked, the app fuses camera-"
    "based tracking with the phone's gyroscope: if the camera briefly loses sight "
    "of the marker, the rendered piece stays put. Browser-based. Must run on modern "
    "iOS Safari and Android Chrome using getUserMedia plus a marker-tracking "
    "library that supports iOS Safari without WebXR -- recommended: MindAR (Image "
    "/ Multi-Target mode) or AR.js NFT (natural-feature tracking). Must be served "
    "over HTTPS. Tracking must be a fused multi-sensor pipeline (VIO-lite). Primary "
    "anchor is the marker via camera; when the marker leaves view rotation is "
    "maintained by gyroscope (DeviceOrientationEvent) with heading drift corrected "
    "by magnetometer. Progressive enhancement: if navigator.xr with WebXR Hit Test "
    "is available, use it. Explicitly do NOT use GPS. Fully static / offline-"
    "capable. AR marker tracking sensor fusion."
)


def test_solar_system_wish_matches_multiple_domains():
    """SPEC-079 wish must hit at least 3d_graphics, educational_content, web_camera_and_media."""
    detail = match_intent_domain_detailed(SOLAR_SYSTEM_WISH)
    matched = set(detail["matched_domains"])
    required = {
        "3d_graphics_visualisation",
        "educational_content",
        "web_camera_and_media",
    }
    missing = required - matched
    assert not missing, (
        f"Solar-system wish missed required domains: {missing}. "
        f"Actual matched: {sorted(matched)}. Confidences: "
        f"{detail['match_confidence_per_domain']}"
    )
    # Broad-match: expect several domains at once, not just the winner.
    assert len(matched) >= 3, f"Broad-match expected >=3 domains, got {matched}"
    # suggested_rr_ids populated
    assert detail["suggested_rr_ids"], "Expected non-empty suggested_rr_ids"
    assert detail["engine_version"] == ENGINE_VERSION


def test_ar_art_wish_matches_ar_and_camera():
    """SPEC-077 wish must include augmented_reality and web_camera_and_media."""
    detail = match_intent_domain_detailed(AR_ART_WISH)
    matched = set(detail["matched_domains"])
    required = {"augmented_reality", "web_camera_and_media"}
    missing = required - matched
    assert not missing, (
        f"AR-art wish missed required domains: {missing}. "
        f"Actual matched: {sorted(matched)}. Confidences: "
        f"{detail['match_confidence_per_domain']}"
    )


def test_empty_wish_still_returns_valid_detail():
    """REQ-111 acceptance: empty match still returns a well-formed detail dict
    so the caller can emit intent_match_completed with empty payload."""
    detail = match_intent_domain_detailed("")
    assert detail["matched_domains"] == []
    assert detail["baseline_rr_ids"] == []
    assert detail["suggested_rr_ids"] == []
    assert detail["match_confidence_per_domain"] == {}
    assert detail["engine_version"] == ENGINE_VERSION


def test_no_match_wish_still_returns_valid_detail():
    """REQ-111 acceptance: a wish with no keyword hits still returns a
    well-formed detail dict."""
    detail = match_intent_domain_detailed("zzz qqq xxx yyy nothing to see here")
    assert detail["matched_domains"] == []
    assert detail["baseline_rr_ids"] == []
    assert detail["suggested_rr_ids"] == []
    assert detail["match_confidence_per_domain"] == {}
    assert detail["engine_version"] == ENGINE_VERSION


def test_legacy_interface_still_works():
    """The two-tuple legacy API must remain compatible."""
    domains, rrs = match_intent_domain(SOLAR_SYSTEM_WISH)
    assert isinstance(domains, list)
    assert isinstance(rrs, list)
    assert "3d_graphics_visualisation" in domains


def test_broad_match_returns_more_than_winner_take_all():
    """Broad-match mode: the solar-system wish should return several domains
    at once, not just the highest-scoring one."""
    detail = match_intent_domain_detailed(SOLAR_SYSTEM_WISH)
    # Even at default threshold 0.15, 3d_graphics + educational_content +
    # web_camera + a few others should qualify.
    assert len(detail["matched_domains"]) >= 4, (
        f"Broad-match expected >=4 domains, got {detail['matched_domains']} "
        f"with confidences {detail['match_confidence_per_domain']}"
    )


def test_confidence_scores_are_in_range():
    detail = match_intent_domain_detailed(SOLAR_SYSTEM_WISH)
    for domain, conf in detail["match_confidence_per_domain"].items():
        assert 0.0 <= conf <= 1.0, f"Domain {domain} has out-of-range confidence {conf}"


def test_threshold_env_var_respected(monkeypatch):
    """Bumping the threshold should shrink the matched-domains list."""
    baseline = match_intent_domain_detailed(SOLAR_SYSTEM_WISH)
    monkeypatch.setenv("ADT_INTENT_MATCH_THRESHOLD", "0.9")
    strict = match_intent_domain_detailed(SOLAR_SYSTEM_WISH)
    assert len(strict["matched_domains"]) <= len(baseline["matched_domains"])
