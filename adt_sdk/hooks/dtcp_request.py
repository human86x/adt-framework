#!/usr/bin/env python3
"""
DTCP Request Hook

CLI wrapper for agents to submit DTCP requests.
Usage:
    dtcp_request.py --action edit --file path/to/file --spec SPEC-017 --rationale "..." --content "..."
"""
import argparse
import json
import sys
import os

# Add parent directory to path so we can import adt_sdk
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from adt_sdk.client import ADTClient

def main():
    parser = argparse.ArgumentParser(description="DTCP Request Hook")
    parser.add_argument("--action", required=True, help="Action type (edit, create, delete, deploy, delegate, etc.)")
    parser.add_argument("--file", help="Target file path")
    parser.add_argument("--spec", required=True, help="Spec reference ID")
    parser.add_argument("--rationale", required=True, help="Rationale for the action")
    parser.add_argument("--content", help="File content (for edit/create)")
    parser.add_argument("--old-string", help="Old string to replace (for patch action)")
    parser.add_argument("--new-string", help="New string to replace with (for patch action)")
    parser.add_argument("--justification", help="Tier 2 justification (if required)")
    parser.add_argument("--target", help="Remote target (for deploy/ftp_sync)")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, do not execute")
    parser.add_argument("--agent", default=os.environ.get("ADT_AGENT", "CLI"), help="Agent name")
    parser.add_argument("--role", default=os.environ.get("ADT_ROLE", "unknown"), help="Agent role")
    
    # SPEC-042: Swarm Delegation parameters
    parser.add_argument("--child-role", help="Child role to spawn (for delegate action)")
    parser.add_argument("--task-id", help="Task ID assigned to the child (for delegate action)")
    parser.add_argument("--spec-ref", help="Authorizing spec for the child (for delegate action)")

    args = parser.parse_args()

    # SPEC-044 Phase B3: Use DTCP_URL with fallback to DTTP_URL
    dtcp_url = os.environ.get("DTCP_URL") or os.environ.get("DTTP_URL") or "http://localhost:5002"

    client = ADTClient(
        dtcp_url=dtcp_url,
        agent_name=args.agent,
        role=args.role
    )

    params = {}
    if args.file:
        params["file"] = args.file
    if args.content:
        params["content"] = args.content
    if args.old_string:
        params["old_string"] = args.old_string
    if args.new_string:
        params["new_string"] = args.new_string
    if args.justification:
        params["tier2_justification"] = args.justification
    if args.target:
        params["target"] = args.target
        
    # SPEC-042: Swarm Delegation parameters
    if args.child_role:
        params["child_role"] = args.child_role
    if args.task_id:
        params["task_id"] = args.task_id
    if args.spec_ref:
        params["spec_ref"] = args.spec_ref

    mode = "dry-run" if args.dry_run else "live"
    print(f"Submitting {args.action} request to DTCP ({mode})...", file=sys.stderr)

    try:
        if args.dry_run:
            response = client.validate_write(
                spec_id=args.spec,
                action=args.action,
                params=params,
                rationale=args.rationale
            )
        else:
            response = client.request(
                spec_id=args.spec,
                action=args.action,
                params=params,
                rationale=args.rationale
            )
        
        # In development mode, the DTCP service only validates. 
        # If it returned 'allowed' but didn't execute, we do it here.
        if response.get("status") == "allowed" and not args.dry_run:
            exec_needed = True
            if "result" in response and "status" in response["result"] and response["result"]["status"] == "success":
                if args.action == "delegate":
                    exec_needed = False
                else:
                    exec_needed = False # If DTCP already executed it (e.g. production mode)
                
            if exec_needed:
                from adt_core.dtcp.actions import ActionHandler
                handler = ActionHandler(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
                local_result = handler.execute(args.action, params, agent=args.agent, role=args.role)
                response["local_execution"] = local_result
                if local_result.get("status") == "success":
                    print("Local execution successful.", file=sys.stderr)
                else:
                    print(f"Local execution failed: {local_result.get('message')}", file=sys.stderr)
                    response["status"] = "error" # Mark as error if execution failed
        
        print(json.dumps(response, indent=2))
        
        if response.get("status") == "allowed":
            sys.exit(0)
        else:
            sys.exit(1)
            
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
