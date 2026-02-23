#!/usr/bin/env python3
"""
DTTP Request Hook

CLI wrapper for agents to submit DTTP requests.
Usage:
    dttp_request.py --action edit --file path/to/file --spec SPEC-017 --rationale "..." --content "..."
"""
import argparse
import json
import sys
import os

# Add parent directory to path so we can import adt_sdk
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from adt_sdk.client import ADTClient

def main():
    parser = argparse.ArgumentParser(description="DTTP Request Hook")
    parser.add_argument("--action", required=True, help="Action type (edit, create, delete, deploy, etc.)")
    parser.add_argument("--file", help="Target file path")
    parser.add_argument("--spec", required=True, help="Spec reference ID")
    parser.add_argument("--rationale", required=True, help="Rationale for the action")
    parser.add_argument("--content", help="File content (for edit/create)")
    parser.add_argument("--old-string", help="Old string to replace (for patch action)")
    parser.add_argument("--new-string", help="New string to replace with (for patch action)")
    parser.add_argument("--target", help="Remote target (for deploy/ftp_sync)")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, do not execute")
    parser.add_argument("--agent", default=os.environ.get("ADT_AGENT", "CLI"), help="Agent name")
    parser.add_argument("--role", default=os.environ.get("ADT_ROLE", "unknown"), help="Agent role")

    args = parser.parse_args()

    client = ADTClient(
        dttp_url=os.environ.get("DTTP_URL", "http://localhost:5002"),
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
    if args.target:
        params["target"] = args.target

    mode = "dry-run" if args.dry_run else "live"
    print(f"Submitting {args.action} request to DTTP ({mode})...", file=sys.stderr)

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
