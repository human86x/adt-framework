import json
import os
import subprocess
import pytest
from adt_core.dttp.config import DTTPConfig
from adt_core.dttp.service import create_dttp_app

@pytest.fixture
def git_repo(tmp_path):
    """Create a real git repo for testing."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    
    # Init git
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_dir, check=True)
    
    # Create initial commit
    readme = repo_dir / "README.md"
    readme.write_text("# Test Repo")
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo_dir, check=True)
    
    # Create a feature branch
    subprocess.run(["git", "checkout", "-b", "feature-1"], cwd=repo_dir, check=True)
    
    return repo_dir

@pytest.fixture
def dttp_app(git_repo):
    """Create a test DTTP service with git repo."""
    project_root = git_repo
    
    # ADS log
    ads_dir = project_root / "_cortex" / "ads"
    ads_dir.mkdir(parents=True)
    ads_path = ads_dir / "events.jsonl"
    ads_path.write_text("")

    # Specs config
    config_dir = project_root / "config"
    config_dir.mkdir()
    specs_config = config_dir / "specs.json"
    specs_config.write_text(json.dumps({
        "specs": {
            "SPEC-023": {
                "status": "approved",
                "roles": ["DevOps_Engineer"],
                "action_types": ["git_commit", "git_push", "git_tag", "edit"],
                "paths": ["./", "README.md"]
            }
        }
    }))

    # Jurisdictions config
    juris_config = config_dir / "jurisdictions.json"
    juris_config.write_text(json.dumps({
        "jurisdictions": {
            "DevOps_Engineer": ["./"]
        }
    }))

    config = DTTPConfig(
        port=5003,
        mode="development",
        ads_path=str(ads_path),
        specs_config=str(specs_config),
        jurisdictions_config=str(juris_config),
        project_root=str(project_root),
        project_name="git-test",
    )

    app = create_dttp_app(config)
    app.config["TESTING"] = True
    return app

@pytest.fixture
def client(dttp_app):
    return dttp_app.test_client()

def test_git_commit_allowed(client, git_repo):
    # Modify a file
    readme = git_repo / "README.md"
    readme.write_text("# Modified")
    
    payload = {
        "agent": "GEMINI",
        "role": "DevOps_Engineer",
        "spec_id": "SPEC-023",
        "action": "git_commit",
        "params": {"message": "test commit", "files": ["README.md"]},
        "rationale": "Testing git_commit"
    }
    resp = client.post("/request", json=payload)
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "allowed"
    
    # Verify commit happened
    res = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=git_repo, capture_output=True, text=True)
    assert "test commit" in res.stdout

def test_git_tag_requires_justification(client):
    payload = {
        "agent": "GEMINI",
        "role": "DevOps_Engineer",
        "spec_id": "SPEC-023",
        "action": "git_tag",
        "params": {"tag": "v1.0.0"},
        "rationale": "Testing git_tag"
    }
    resp = client.post("/request", json=payload)
    assert resp.status_code == 403
    assert "tier2_justification_required" in resp.get_json()["reason"]

def test_git_tag_with_justification(client, git_repo):
    payload = {
        "agent": "GEMINI",
        "role": "DevOps_Engineer",
        "spec_id": "SPEC-023",
        "action": "git_tag",
        "params": {
            "tag": "v1.0.0",
            "tier2_justification": "Official release"
        },
        "rationale": "Testing git_tag"
    }
    resp = client.post("/request", json=payload)
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "allowed"
    
    # Verify tag exists
    res = subprocess.run(["git", "tag"], cwd=git_repo, capture_output=True, text=True)
    assert "v1.0.0" in res.stdout

def test_git_push_main_requires_justification(client):
    payload = {
        "agent": "GEMINI",
        "role": "DevOps_Engineer",
        "spec_id": "SPEC-023",
        "action": "git_push",
        "params": {"branch": "main"},
        "rationale": "Testing git_push main"
    }
    resp = client.post("/request", json=payload)
    assert resp.status_code == 403
    assert "tier2_justification_required" in resp.get_json()["reason"]

def test_git_push_feature_branch_allowed(client, git_repo):
    payload = {
        "agent": "GEMINI",
        "role": "DevOps_Engineer",
        "spec_id": "SPEC-023",
        "action": "git_push",
        "params": {"branch": "feature-1"},
        "rationale": "Testing git_push feature branch"
    }
    resp = client.post("/request", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "allowed"
