"""SPEC-078 Post-Forge Governance Repairs — regression tests.

Covers three Backend edits from the operator directive dated 2026-08-03:

- Part A (REQ-118): POST /api/specs rejects duplicate spec_id with 409 and
  tags the ADS ``spec_created`` event with ``allocation_source``.
- Part B (REQ-119): the Forge Architect prompt template forbids SPEC-001
  as a child spec ID (surface check on the markdown file).
- Part C (REQ-120): ``get_project_paths(name)`` for an unknown project no
  longer silently falls back to the framework root.

Each test is independent so a single failure names the exact defect.
"""
import json
import os

import pytest

from adt_core.registry import ProjectRegistry


REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FORGE_PROMPT = os.path.join(REPO, "adt_center/api/forge_prompts/architect.md")


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    """A test client backed by a two-project registry rooted in tmp_path.

    Mocks the ``ProjectRegistry`` used inside ``adt_center.app`` so the app
    does not touch the operator's real ``~/.adt/projects.json`` registry.
    """
    home = tmp_path / "home"
    home.mkdir()
    registry_path = home / ".adt" / "projects.json"

    proj_dir = tmp_path / "proj"
    (proj_dir / "_cortex" / "specs").mkdir(parents=True)
    (proj_dir / "_cortex" / "ads").mkdir(parents=True)
    (proj_dir / "_cortex" / "standards").mkdir(parents=True)
    (proj_dir / "config").mkdir(parents=True)
    (proj_dir / "_cortex" / "ads" / "events.jsonl").write_text("")
    (proj_dir / "_cortex" / "tasks.json").write_text(
        json.dumps({"project": "proj", "tasks": []})
    )

    reg = ProjectRegistry(str(registry_path))
    reg.register_project("proj", str(proj_dir))

    import adt_center.app as center_app
    monkeypatch.setattr(center_app, "ProjectRegistry",
                        lambda: ProjectRegistry(str(registry_path)))

    app = center_app.create_app()
    app.config["TESTING"] = True
    return app, proj_dir


# --------------------------------------------------------------------------
# Part A: POST /api/specs collision + allocation_source
# --------------------------------------------------------------------------

def _post_spec(client, project, payload):
    return client.post(
        f"/api/specs?project={project}",
        data=json.dumps(payload),
        content_type="application/json",
    )


def test_part_a_null_spec_id_on_empty_project_allocates_spec_001(isolated_app):
    """REQ-118 acceptance case #2: null spec_id → server allocates SPEC-001."""
    app, proj_dir = isolated_app
    client = app.test_client()

    resp = _post_spec(client, "proj", {
        "title": "First",
        "intent": "First child intent.",
        "success_condition": "It exists.",
    })
    assert resp.status_code == 201, resp.data
    body = resp.get_json()
    assert body["spec_id"] == "SPEC-001"
    assert body["allocation_source"] == "server"

    # File written to the project's spec dir, not the framework's.
    assert any(
        f.startswith("SPEC-001_") and f.endswith(".md")
        for f in os.listdir(proj_dir / "_cortex" / "specs")
    )


def test_part_a_duplicate_spec_id_returns_409(isolated_app):
    """REQ-118 acceptance case #1: colliding spec_id → 409, no file, no ADS."""
    app, proj_dir = isolated_app
    client = app.test_client()

    # Seed a SPEC-001 on disk.
    (proj_dir / "_cortex" / "specs" / "SPEC-001_VISION.md").write_text(
        "# SPEC-001: Vision\n"
    )
    ads_before = (proj_dir / "_cortex" / "ads" / "events.jsonl").read_text()

    resp = _post_spec(client, "proj", {
        "spec_id": "SPEC-001",
        "title": "Camera Pipeline",
        "intent": "Should be rejected.",
        "success_condition": "Never written.",
    })
    assert resp.status_code == 409, resp.data
    body = resp.get_json()
    assert body["error"] == "spec_id_collision"
    assert body["existing_file"] == "SPEC-001_VISION.md"
    assert "existing_title" in body

    # No colliding file written.
    files = os.listdir(proj_dir / "_cortex" / "specs")
    assert files == ["SPEC-001_VISION.md"]

    # No ADS event emitted for the rejected write.
    ads_after = (proj_dir / "_cortex" / "ads" / "events.jsonl").read_text()
    assert ads_after == ads_before


def test_part_a_client_supplied_id_tags_allocation_source(isolated_app):
    """A client-supplied non-colliding ID is tagged ``allocation_source=client``."""
    app, proj_dir = isolated_app
    client = app.test_client()

    resp = _post_spec(client, "proj", {
        "spec_id": "SPEC-042",
        "title": "Explicit",
        "intent": "Explicit ID.",
        "success_condition": "Assigned.",
    })
    assert resp.status_code == 201, resp.data
    body = resp.get_json()
    assert body["spec_id"] == "SPEC-042"
    assert body["allocation_source"] == "client"

    # ADS event carries allocation_source in action_data.
    ads_lines = [
        line for line in
        (proj_dir / "_cortex" / "ads" / "events.jsonl")
        .read_text().splitlines()
        if line.strip()
    ]
    assert ads_lines, "spec_created ADS event should have been logged"
    evt = json.loads(ads_lines[-1])
    assert evt["action_type"] == "spec_created"
    assert evt["action_data"]["allocation_source"] == "client"
    assert evt["action_data"]["spec_id"] == "SPEC-042"


def test_part_a_server_allocation_skips_ids_present_on_disk(isolated_app):
    """Server allocation must scan the on-disk specs dir too, not only
    ``config/specs.json`` — otherwise a fresh project with a hand-placed
    SPEC-001 would get SPEC-001 allocated again on the next null-ID POST."""
    app, proj_dir = isolated_app
    client = app.test_client()

    (proj_dir / "_cortex" / "specs" / "SPEC-001_VISION.md").write_text(
        "# SPEC-001: Vision\n"
    )

    resp = _post_spec(client, "proj", {
        "title": "Next",
        "intent": "Should not collide.",
        "success_condition": "Assigned SPEC-002 or higher.",
    })
    assert resp.status_code == 201, resp.data
    body = resp.get_json()
    assert body["spec_id"] == "SPEC-002"
    assert body["allocation_source"] == "server"


# --------------------------------------------------------------------------
# Part B: architect.md prompt surface check
# --------------------------------------------------------------------------

def test_part_b_architect_prompt_reserves_spec_001():
    """REQ-119: the Phase B section must forbid SPEC-001 as a child ID."""
    with open(FORGE_PROMPT, "r", encoding="utf-8") as f:
        prompt = f.read()

    # Must call out the reservation explicitly.
    assert "SPEC-002" in prompt
    assert "SPEC-001" in prompt
    assert "reserved" in prompt.lower()

    # Must contain a negative instruction against posting SPEC-001 in Phase B.
    lowered = prompt.lower()
    assert (
        'never post `spec_id: "spec-001"`' in lowered
        or 'never post `spec_id: spec-001`' in lowered
        or 'never post spec-001' in lowered
    ), "Prompt should explicitly forbid POSTing SPEC-001 as a child."

    # Any example curl in Phase B must not put SPEC-001 in spec_id. The
    # Phase A ADS event legitimately references SPEC-001 (the Vision spec
    # being reported on), so only Phase B onwards is checked.
    phase_b_marker = "## Phase B"
    idx = prompt.find(phase_b_marker)
    assert idx != -1, "Prompt should contain a Phase B section header."
    phase_b = prompt[idx:]
    assert '"spec_id":"SPEC-001"' not in phase_b
    assert '"spec_id": "SPEC-001"' not in phase_b


# --------------------------------------------------------------------------
# Part C: get_project_paths safety belt
# --------------------------------------------------------------------------

def test_part_c_unknown_project_does_not_return_framework_root(isolated_app):
    """REQ-120 Backend safety belt: ``get_project_paths('nonexistent')`` must
    NOT silently return framework paths, because that made forgotten
    ``?project=`` fetches bleed the 89 framework specs into project views.
    """
    app, _proj_dir = isolated_app

    framework_paths = app.get_project_paths(None)
    unknown_paths = app.get_project_paths("does-not-exist-anywhere")

    assert unknown_paths["specs"] != framework_paths["specs"], (
        "Unknown project must not return the framework's specs dir; that "
        "recreates REQ-120's silent bleed."
    )
    assert unknown_paths.get("unknown_project") is True
    assert unknown_paths["name"] == "does-not-exist-anywhere"
    # The sentinel path should not exist — that is the whole point (empty
    # result set surfaces the mis-scoped call).
    assert not os.path.exists(unknown_paths["specs"])


def test_part_c_known_project_still_returns_project_paths(isolated_app):
    """Regression guard: the safety belt must not break normal project lookups."""
    app, proj_dir = isolated_app

    paths = app.get_project_paths("proj")
    assert paths["root"] == str(proj_dir)
    assert paths["specs"] == str(proj_dir / "_cortex" / "specs")
    assert paths.get("unknown_project") is False


def test_part_c_none_still_returns_framework_root(isolated_app):
    """Regression guard: passing name=None keeps the framework default."""
    app, _ = isolated_app

    paths = app.get_project_paths(None)
    assert paths["root"] == app.FRAMEWORK_ROOT
    assert paths.get("unknown_project") is False
