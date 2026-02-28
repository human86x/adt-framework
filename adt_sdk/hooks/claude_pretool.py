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
import re

import requests

# Tool names this hook intercepts
INTERCEPTED_TOOLS = {"Write", "Edit", "NotebookEdit"}
READ_TOOLS = {"Read", "Glob", "Grep"}
BASH_TOOLS = {"Bash"}

# Patterns that indicate file write operations in shell commands
BASH_WRITE_OPERATORS = re.compile(
    r'(?:'
    r'>\s*\S'           # > redirect (overwrite)
    r'|>>\s*\S'         # >> redirect (append)
    r'|\btee\b'         # tee command
    r'|\bdd\b.*\bof='   # dd with output file
    r'|\binstall\b'     # install command
    r'|\bmkdir\b'       # mkdir
    r'|\brmdir\b'       # rmdir
    r'|\brm\b'          # rm
    r'|\bmv\b'          # mv (destination could be outside)
    r'|\bcp\b'          # cp (destination could be outside)
    r'|\bln\b'          # ln (symlink creation)
    r'|\bchmod\b'       # chmod
    r'|\bchown\b'       # chown
    r'|\btouch\b'       # touch
    r'|\bsed\b.*-i'     # sed in-place
    r'|\bpatch\b'       # patch command
    r'|\bgit\s+push'    # git push
    r'|\bsudo\b'        # sudo anything
    r'|\bsu\b'          # su
    r')'
)

# Regex to extract absolute paths and ~/ paths from a shell command
BASH_PATH_RE = re.compile(
    r'(?:'
    r'(?<![a-zA-Z0-9_])(/[a-zA-Z0-9_./-]{2,})'  # /absolute/path
    r'|(?<![a-zA-Z0-9_])(~/[a-zA-Z0-9_./-]*)'     # ~/home-relative
    r')'
)

# Sensitive path prefixes that are never allowed in sandbox
SENSITIVE_PATHS = [
    "/etc/", "/root/", "/var/", "/proc/", "/sys/", "/dev/",
    "/boot/", "/sbin/", "/usr/sbin/",
]

# Sensitive home-directory paths
SENSITIVE_HOME_PATHS = [
    ".ssh", ".aws", ".azure", ".gcloud", ".config/gcloud",
    ".kube", ".docker", ".gnupg", ".npmrc", ".pypirc",
    ".netrc", ".env",
]


def check_bash_sandbox(command: str, project_dir: str) -> str:
    """Check if a Bash command violates sandbox containment.

    Returns empty string if allowed, or a denial reason if blocked.
    """
    full_project_dir = os.path.realpath(project_dir)
    home_dir = os.path.expanduser("~")

    # Unconditionally blocked commands in sandbox
    if re.search(r'\bsudo\b', command):
        return "SANDBOX: 'sudo' is not permitted in sandbox mode."
    if re.search(r'\bsu\s', command):
        return "SANDBOX: 'su' is not permitted in sandbox mode."

    # Extract all paths from the command
    paths_found = []
    for match in BASH_PATH_RE.finditer(command):
        abs_path = match.group(1)
        home_path = match.group(2)
        if abs_path:
            paths_found.append(abs_path)
        elif home_path:
            # Expand ~/... to absolute
            expanded = os.path.expanduser(home_path)
            paths_found.append(expanded)

    # Check each path for containment
    for path in paths_found:
        resolved = os.path.realpath(path)

        # Check sensitive system paths
        for sensitive in SENSITIVE_PATHS:
            if resolved.startswith(sensitive) or resolved == sensitive.rstrip("/"):
                return (
                    f"SANDBOX: Bash command references sensitive path {path}. "
                    f"Agents cannot access system paths in sandbox mode."
                )

        # Check sensitive home paths
        for home_sensitive in SENSITIVE_HOME_PATHS:
            sensitive_full = os.path.join(home_dir, home_sensitive)
            if resolved.startswith(sensitive_full) or resolved == sensitive_full:
                return (
                    f"SANDBOX: Bash command references sensitive path {path}. "
                    f"Agents cannot access credentials/keys in sandbox mode."
                )

        # If command has write operators, check path containment
        if BASH_WRITE_OPERATORS.search(command):
            is_contained = (
                resolved == full_project_dir
                or resolved.startswith(full_project_dir + os.sep)
            )
            if not is_contained:
                return (
                    f"SANDBOX: Bash write operation targets path outside project root: {path}. "
                    f"All file modifications must be within {project_dir}."
                )

    # Check for scripting one-liners that can write anywhere (regardless of shell operators)
    scripting_write = re.search(
        r'(?:'
        r'python[23]?\s+-c\s+.*(?:open|write|Path)'
        r'|node\s+-e\s+.*(?:writeFile|appendFile|fs\.)'
        r'|ruby\s+-e\s+.*(?:File\.write|File\.open|IO\.write)'
        r'|perl\s+-e\s+.*(?:open|print\s+\w+\s)'
        r')',
        command,
    )
    if scripting_write:
        return (
            "SANDBOX: Bash command contains scripting language with file write "
            "operations. Use Write/Edit tools instead for governed file access."
        )

    return ""  # Allowed


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
    if tool_name in {"Read", "Write", "Edit"}:
        return tool_input.get("file_path", "")
    elif tool_name == "Glob":
        return tool_input.get("directory_path", "")
    elif tool_name == "Grep":
        return tool_input.get("directory_path", "")
    elif tool_name == "NotebookEdit":
        return tool_input.get("file_path", "")
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


def get_canonical_role(role: str, project_dir: str) -> str:
    """Normalize role name against project's jurisdiction config."""
    if not role:
        return role
    jur_path = os.path.join(project_dir, "config", "jurisdictions.json")
    if os.path.exists(jur_path):
        try:
            with open(jur_path) as f:
                jur = json.load(f)
            for canonical in jur.get("jurisdictions", {}).keys():
                if role.lower() == canonical.lower():
                    return canonical
        except:
            pass
    return role


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


def submit_scr(dttp_url: str, agent: str, role: str, spec_id: str,
               target_path: str, action: str, params: dict) -> dict:
    """Submit a Sovereign Change Request to the ADT Panel."""
    # Derive Panel URL (usually port 5001 on the same host)
    from urllib.parse import urlparse
    parsed = urlparse(dttp_url)
    panel_url = f"{parsed.scheme}://{parsed.hostname}:5001"
    
    # Try to determine project name from dttp_url port if not default
    project_name = None
    if parsed.port and parsed.port != 5002:
        # For external projects, port is usually in registry
        # We'll let the Panel handle it via IP or let the agent pass it if we can find it
        pass

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

    # Intercept write tools OR read tools (if sandboxed) OR bash (if sandboxed)
    is_write = tool_name in INTERCEPTED_TOOLS
    is_read = tool_name in READ_TOOLS
    is_bash = tool_name in BASH_TOOLS
    adt_sandbox = os.environ.get("ADT_SANDBOX") == "1"

    if not is_write and not (is_read and adt_sandbox) and not (is_bash and adt_sandbox):
        sys.exit(0)

    tool_input = hook_input.get("tool_input", {})

    # Configuration from environment
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR",
                                 hook_input.get("cwd", os.getcwd()))
    dttp_url = os.environ.get("DTTP_URL", read_project_dttp_url(project_dir))
    agent = os.environ.get("ADT_AGENT", "CLAUDE")
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
    
    # SPEC-020 Amendment B: Normalize role name
    role = get_canonical_role(role, project_dir)

    if not spec_id:
        spec_id = "SPEC-017"

    # SPEC-036: Bash sandbox enforcement
    if is_bash and adt_sandbox:
        bash_command = tool_input.get("command", "")
        denial = check_bash_sandbox(bash_command, project_dir)
        if denial:
            print(json.dumps(make_deny(denial)))
            sys.exit(0)
        # Bash passed sandbox check -- allow
        print(json.dumps(make_allow("SANDBOX: Bash command passed containment check")))
        sys.exit(0)

    # Extract and convert file path
    abs_path = extract_file_path(tool_name, tool_input)
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
    if rel_path == "_cortex/requests.md" and tool_name == "Write":
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
                # Claude Code hook format for allowing/denying
                print(json.dumps(make_allow(f"Request transparently filed via governed API: {result.get('req_id')}")))
                sys.exit(0)

    # Build DTTP action and params
    action, params = build_dttp_params(tool_name, tool_input, rel_path)
    
    # Add tier2_justification if provided in environment
    tier2_justification = os.environ.get("ADT_TIER2_JUSTIFICATION")
    if tier2_justification:
        params["tier2_justification"] = tier2_justification

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
