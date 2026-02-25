#!/usr/bin/env python3
"""
Gemini CLI BeforeTool Enforcement Hook

DTTP-enforced write sandboxing for Gemini CLI agent sessions.
Intercepts write_file and replace tools, routes all file modifications
through the DTTP gateway for validation and (in production mode) execution.

Development mode: dry_run validation; allows if DTTP approves, denies if rejected.
Production mode: DTTP executes the write; always denies Gemini's direct tool use.
Fail-closed: if DTTP is unreachable, deny the tool call.

Environment variables:
    DTTP_URL              - DTTP service URL (default: http://localhost:5002)
    ADT_AGENT             - Agent identifier (default: GEMINI)
    ADT_ROLE              - Agent role (default: Backend_Engineer)
    ADT_SPEC_ID           - Active spec reference (default: SPEC-017)
    ADT_ENFORCEMENT_MODE  - "development" or "production" (default: development)
    GEMINI_PROJECT_DIR    - Project root for path resolution

Reads Gemini CLI hook JSON from stdin. Outputs hook decision JSON to stdout.
Exit code 0 = decision provided. Exit code 2 = blocking error.
"""
import json
import os
import sys
import re

import requests

# Gemini CLI tool names for file modification
INTERCEPTED_TOOLS = {"write_file", "replace"}
READ_TOOLS = {"read_file", "list_files", "search_files"}


def make_deny(reason: str) -> dict:
    """Create a deny decision JSON (Gemini CLI format)."""
    return {
        "decision": "deny",
        "reason": reason,
    }


def make_allow(reason: str = "") -> dict:
    """Create an allow decision JSON (Gemini CLI format)."""
    result = {"decision": "allow"}
    if reason:
        result["reason"] = reason
    return result


def to_project_relative(abs_path: str, project_dir: str) -> str:
    """Convert an absolute file path to a project-relative path."""
    abs_path = os.path.realpath(abs_path)
    project_dir = os.path.realpath(project_dir)
    if abs_path.startswith(project_dir + os.sep):
        return abs_path[len(project_dir) + 1:]
    if abs_path == project_dir:
        return "."
    # Path is outside project -- return as-is, DTTP will reject
    return abs_path


def extract_file_path(tool_name: str, tool_input: dict) -> str:
    """Extract the target file path from Gemini CLI tool input."""
    if tool_name in {"read_file", "replace", "write_file"}:
        return tool_input.get("file_path", "")
    elif tool_name == "list_files":
        return tool_input.get("dir_path", "")
    elif tool_name == "search_files":
        return tool_input.get("dir_path", "")
    return tool_input.get("file_path", "")


def read_project_dttp_url(project_dir: str) -> str:
    """Read DTTP port from <project_dir>/config/dttp.json."""
    dttp_json = os.path.join(project_dir, "config", "dttp.json")
    if os.path.exists(dttp_json):
        try:
            with open(dttp_json) as f:
                data = json.load(f)
                port = data.get("port")
                if port:
                    return f"http://localhost:{port}"
        except:
            pass
    return "http://localhost:5002"  # fallback


def build_dttp_params(tool_name: str, tool_input: dict, rel_path: str) -> tuple:
    """Build DTTP action and params from Gemini CLI tool input.

    Returns (action, params) tuple.
    """
    if tool_name == "write_file":
        return "edit", {
            "file": rel_path,
            "content": tool_input.get("content", ""),
        }
    elif tool_name == "replace":
        return "patch", {
            "file": rel_path,
            "old_string": tool_input.get("old_string", ""),
            "new_string": tool_input.get("new_string", ""),
        }
    return "edit", {"file": rel_path}


def query_dttp(dttp_url: str, agent: str, role: str, spec_id: str,
               action: str, params: dict, rationale: str,
               dry_run: bool = False) -> dict:
    """Send a request to the DTTP service. Returns the response dict."""
    payload = {
        "agent": agent,
        "role": role,
        "spec_id": spec_id,
        "action": action,
        "params": params,
        "rationale": rationale,
        "dry_run": dry_run,
    }
    response = requests.post(f"{dttp_url}/request", json=payload, timeout=10)
    return response.json()


def submit_scr(dttp_url: str, agent: str, role: str, spec_id: str,
               target_path: str, action: str, params: dict) -> dict:
    """Submit a Sovereign Change Request to the ADT Panel."""
    # Derive Panel URL (usually port 5001 on the same host)
    from urllib.parse import urlparse
    parsed = urlparse(dttp_url)
    panel_url = f"{parsed.scheme}://{parsed.hostname}:5001"

    scr_payload = {
        "agent": agent,
        "role": role,
        "spec_ref": spec_id,
        "target_path": target_path,
        "description": f"Agent proposed {action} on sovereign path {target_path}",
    }
    
    if action == "edit":
        scr_payload["change_type"] = "full_replace"
        scr_payload["content"] = params.get("content", "")
    elif action == "patch":
        scr_payload["change_type"] = "patch"
        scr_payload["patch"] = {
            "old_string": params.get("old_string", ""),
            "new_string": params.get("new_string", "")
        }
    
    try:
        resp = requests.post(f"{panel_url}/api/governance/sovereign-requests", 
                             json=scr_payload, timeout=5)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def main():
    # Read hook input from stdin
    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        # Can't parse input -- fail closed
        print(json.dumps(make_deny("DTTP hook: failed to parse hook input")))
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")

    # Intercept write tools OR read tools (if sandboxed)
    is_write = tool_name in INTERCEPTED_TOOLS
    is_read = tool_name in READ_TOOLS
    adt_sandbox = os.environ.get("ADT_SANDBOX") == "1"

    if not is_write and not (is_read and adt_sandbox):
        sys.exit(0)

    tool_input = hook_input.get("tool_input", {})

    # Configuration from environment
    project_dir = os.environ.get("GEMINI_PROJECT_DIR",
                                 hook_input.get("cwd", os.getcwd()))
    dttp_url = os.environ.get("DTTP_URL", read_project_dttp_url(project_dir))
    agent = os.environ.get("ADT_AGENT", "GEMINI")
    enforcement_mode = os.environ.get("ADT_ENFORCEMENT_MODE", "development")

    # SPEC-037: Fix role priority (env var first, then file fallback)
    role = os.environ.get("ADT_ROLE")
    if not role:
        role_file = os.path.join(project_dir, "_cortex", "ops", "active_role.txt")
        if os.path.exists(role_file):
            try:
                with open(role_file) as rf:
                    file_role = rf.read().strip()
                    if file_role:
                        role = file_role
            except OSError:
                pass  # Fall back to default
    
    # Active spec still from file if available, or env var
    spec_id = os.environ.get("ADT_SPEC_ID")
    spec_file = os.path.join(project_dir, '_cortex', 'ops', 'active_spec.txt')
    if os.path.exists(spec_file):
        try:
            with open(spec_file) as sf:
                file_spec = sf.read().strip()
                if file_spec:
                    spec_id = file_spec
        except OSError:
            pass

    if not role:
        role = "Backend_Engineer"
    if not spec_id:
        spec_id = "SPEC-017"

    # Extract and convert file path
    abs_path = extract_file_path(tool_name, hook_input.get("tool_input", {}))
    if not abs_path:
        sys.exit(0)

    # SPEC-036: Resolution and containment check
    full_abs_path = os.path.realpath(abs_path)
    full_project_dir = os.path.realpath(project_dir)
    
    is_contained = (full_abs_path == full_project_dir or 
                    full_abs_path.startswith(full_project_dir + os.sep))

    if adt_sandbox and not is_contained:
        print(json.dumps(make_deny(f"SANDBOX VIOLATION: Path {abs_path} is outside project root.")))
        sys.exit(0)

    rel_path = to_project_relative(abs_path, project_dir)

    # If it's a read tool and we reached here, it passed containment (if sandboxed)
    if is_read:
        print(json.dumps(make_allow(f"DTTP allowed {tool_name} on {rel_path}")))
        sys.exit(0)

    # SPEC-037: Redirect requests.md append to API
    if rel_path == "_cortex/requests.md" and tool_name == "write_file":
        content = tool_input.get("content", "")
        if "## REQ-" in content:
            # Attempt to file via API
            from adt_sdk.client import ADTClient
            client = ADTClient(dttp_url=dttp_url, agent_name=agent, role=role)
            
            # Simple extraction from markdown
            title_match = re.search(r"## REQ-\d+: (.*)", content)
            title = title_match.group(1) if title_match else "Redirected Request"
            to_match = re.search(r"\*\*To:\*\* @?([a-zA-Z_]+)", content)
            to_role = to_match.group(1) if to_match else "Systems_Architect"
            
            desc_part = content.split("### Description")
            description = desc_part[1].split("### Status")[0].strip() if len(desc_part) > 1 else content
            
            result = client.file_request(to_role=to_role, title=title, description=description)
            if result.get("status") == "success":
                print(json.dumps(make_allow(f"Request transparently filed via governed API: {result.get('req_id')}")))
                sys.exit(0)

    # Build DTTP action and params
    action, params = build_dttp_params(tool_name, tool_input, rel_path)
    
    # Add tier2_justification if provided in environment
    tier2_justification = os.environ.get("ADT_TIER2_JUSTIFICATION")
    if tier2_justification:
        params["tier2_justification"] = tier2_justification
        
    rationale = f"Gemini CLI {tool_name} tool: {rel_path}"

    try:
        if enforcement_mode == "production":
            # Production: DTTP executes the write, always deny Gemini's tool
            result = query_dttp(dttp_url, agent, role, spec_id,
                                action, params, rationale, dry_run=False)
            if result.get("status") == "allowed":
                # DTTP wrote the file -- deny Gemini's write (already done)
                print(json.dumps(make_deny(
                    f"DTTP executed {action} on {rel_path} (production mode). "
                    f"File written by DTTP service."
                )))
            else:
                # DTTP denied
                reason = result.get("reason", "unknown")
                print(json.dumps(make_deny(
                    f"DTTP denied {action} on {rel_path}: {reason}"
                )))
        else:
            # Development: dry-run validation only
            result = query_dttp(dttp_url, agent, role, spec_id,
                                action, params, rationale, dry_run=True)
            if result.get("status") == "allowed":
                # Validation passed -- allow Gemini to write directly
                print(json.dumps(make_allow(
                    f"DTTP validated {action} on {rel_path} (development mode)"
                )))
            else:
                # Validation failed -- deny
                reason = result.get("reason", "unknown")
                
                # SPEC-033: Auto-submit SCR on sovereign path violation
                if reason == "sovereign_path_violation":
                    scr_result = submit_scr(dttp_url, agent, role, spec_id, rel_path, action, params)
                    if "scr_id" in scr_result:
                        print(json.dumps(make_deny(
                            f"SOVEREIGN PATH VIOLATION: {rel_path} is protected. "
                            f"Change request {scr_result['scr_id']} has been submitted for human authorization in the ADT Panel."
                        )))
                    else:
                        print(json.dumps(make_deny(
                            f"SOVEREIGN PATH VIOLATION: {rel_path} is protected. "
                            f"Failed to auto-submit change request: {scr_result.get('error', 'unknown error')}"
                        )))
                else:
                    print(json.dumps(make_deny(
                        f"DTTP denied {action} on {rel_path}: {reason}"
                    )))
    except requests.ConnectionError:
        # Fail-closed: DTTP unreachable
        print(json.dumps(make_deny(
            f"DTTP service unreachable at {dttp_url}. "
            f"Fail-closed: all writes blocked until DTTP is available."
        )))
    except requests.Timeout:
        print(json.dumps(make_deny(
            f"DTTP service timeout at {dttp_url}. "
            f"Fail-closed: write blocked."
        )))
    except Exception as e:
        print(json.dumps(make_deny(
            f"DTTP hook error: {e}. Fail-closed: write blocked."
        )))

    sys.exit(0)


if __name__ == "__main__":
    main()
