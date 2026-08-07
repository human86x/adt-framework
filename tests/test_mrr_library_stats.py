"""SPEC-080 / REQ-123: tests for the Framework Standards Catalog endpoint.

Exercises the pure compute function so the tests don't depend on a running
adt-center. Four assertions:
  1. Response has the documented top-level shape.
  2. Standards list is non-empty AND each entry has id + title + source_file.
  3. Domains list is non-empty AND each entry has name + keyword_count + baseline_rr_ids.
  4. engine_version matches the intent_matcher module's ENGINE_VERSION constant.
"""
import re

from adt_center.api.governance_routes import _mrr_library_stats_compute
from adt_core.standards.intent_matcher import ENGINE_VERSION


def test_library_stats_shape():
    payload = _mrr_library_stats_compute()
    for key in (
        "standards_count", "standards",
        "domains_count", "domains",
        "engine_version", "catalog_mtime_iso", "domains_index_file",
    ):
        assert key in payload, f"missing top-level key: {key}"
    # counts consistent with their list lengths
    assert payload["standards_count"] == len(payload["standards"])
    assert payload["domains_count"] == len(payload["domains"])
    # ISO-8601-ish mtime (either None if files missing, or 'YYYY-...Z')
    if payload["catalog_mtime_iso"] is not None:
        assert re.match(r"^\d{4}-\d{2}-\d{2}T", payload["catalog_mtime_iso"])
        assert payload["catalog_mtime_iso"].endswith("Z")


def test_standards_non_empty_and_well_formed():
    payload = _mrr_library_stats_compute()
    assert payload["standards_count"] > 0, "no standards loaded from rationalised_rules.jsonl"
    for std in payload["standards"]:
        assert std.get("id"), f"standard missing id: {std}"
        assert "title" in std
        assert std["source_file"] == "_cortex/standards/rationalised_rules.jsonl"
        # tier may be None (absent in file) — that is allowed by the schema


def test_domains_non_empty_and_well_formed():
    payload = _mrr_library_stats_compute()
    assert payload["domains_count"] > 0, "no domains loaded from intent_index.json"
    for dom in payload["domains"]:
        assert dom.get("name"), f"domain missing name: {dom}"
        assert isinstance(dom.get("keyword_count"), int)
        assert dom["keyword_count"] >= 0
        assert isinstance(dom.get("baseline_rr_ids"), list)
    assert payload["domains_index_file"] == "config/intent_index.json"


def test_engine_version_matches_module():
    payload = _mrr_library_stats_compute()
    assert payload["engine_version"] == ENGINE_VERSION
