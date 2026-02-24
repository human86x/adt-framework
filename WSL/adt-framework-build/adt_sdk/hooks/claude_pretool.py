#!/usr/bin/env python3
"""
Claude Code PreToolUse Enforcement Hook

DTTP-enforced write sandboxing for Claude Code agent sessions.
Intercepts Write, Edit, and NotebookEdit tools, routes all file modifications
through the DTTP gateway for validation and (in production mode) execution.

Development mode: dry_run validation; allows if DTTP approves, denies if rejected.
Production mode: DTTP executes the write; always denies Claude's direct tool use.
Fail-closed: if DTTP is unreachable, deny the tool call.

Environment variables:
    DTTP_URL              - DTTP service URL (default: http://localhost:5002)
    ADT_AGENT             - Agent identifier (default: CLAUDE)
    ADT_ROLE              - Agent role (default: Backend_Engineer)
    ADT_SPEC_ID           - Active spec reference (default: SPEC-017)
    ADT_ENFORCEMENT_MODE  - "development" or "production" (default: development)
    CLAUDE_PROJECT_DIR    - Project root for path resolution (set by Claude Code)

Reads Claude Code hook JSON from stdin. Outputs hook decision JSON to stdout.
Exit code 0 = decision provided. Exit code 2 = blocking error.
"""
import json
import os
import sys

import requests

# Tool names this hook intercepts
INTERCEPTED_TOOLS = {"Write", "Edit", "NotebookEdit"}


def make_deny(reason: str) -> dict:
    """Create a deny decision JSON."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def make_allow(reason: str = "") -> dict:
    """Create an allow decision JSON."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": reason,
        }
    }


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
    """Extract the target file path from tool input."""
    return tool_input.get("file_path", "")


def build_dttp_params(tool_name: str, tool_input: dict, rel_path: str) -> tuple:
    """Build DTTP action and params from Claude Code tool input.

    Returns (action, params) tuple.
    """
    if tool_name == "Write":
        return "edit", {
            "file": rel_path,
            "content": tool_input.get("content", ""),
        }
    elif tool_name == "Edit":
        return "patch", {
            "file": rel_path,
            "old_string": tool_input.get("old_string", ""),
            "new_string": tool_input.get("new_string", ""),
        }
    elif tool_name == "NotebookEdit":
        return "edit", {
            "file": rel_path,
            "content": tool_input.get("new_source", ""),
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


def main():
    # Read hook input from stdin
    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        # Can't parse input -- fail closed
        print(json.dumps(make_deny("DTTP hook: failed to parse hook input")))
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")

    # Only intercept write tools
    if tool_name not in INTERCEPTED_TOOLS:
        sys.exit(0)

    tool_input = hook_input.get("tool_input", {})

    # Configuration from environment
    dttp_url = os.environ.get("DTTP_URL", "http://localhost:5002")
    agent = os.environ.get("ADT_AGENT", "CLAUDE")
    role = os.environ.get("ADT_ROLE", "Backend_Engineer")
    spec_id = os.environ.get("ADT_SPEC_ID", "SPEC-017")
    enforcement_mode = os.environ.get("ADT_ENFORCEMENT_MODE", "development")
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR",
                                 hook_input.get("cwd", os.getcwd()))

    # Extract and convert file path
    abs_path = extract_file_path(tool_name, tool_input)
    if not abs_path:
        # No file path -- let it through (shouldn't happen for write tools)
        sys.exit(0)

    rel_path = to_project_relative(abs_path, project_dir)

    # Build DTTP action and params
    action, params = build_dttp_params(tool_name, tool_input, rel_path)
    rationale = f"Claude Code {tool_name} tool: {rel_path}"

    try:
        if enforcement_mode == "production":
            # Production: DTTP executes the write, always deny Claude's tool
            result = query_dttp(dttp_url, agent, role, spec_id,
                                action, params, rationale, dry_run=False)
            if result.get("status") == "allowed":
                # DTTP wrote the file -- deny Claude's write (already done)
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
                # Validation passed -- allow Claude to write directly
                print(json.dumps(make_allow(
                    f"DTTP validated {action} on {rel_path} (development mode)"
                )))
            else:
                # Validation failed -- deny
                reason = result.get("reason", "unknown")
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
