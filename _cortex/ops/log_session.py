import argparse
import datetime
import uuid
import os
import sys

# Add current dir to path
sys.path.append(os.getcwd())

from adt_core.ads.logger import ADSLogger
from adt_core.ads.schema import ADSEventSchema

def main():
    parser = argparse.ArgumentParser(description="ADT Session Logger")
    parser.add_argument("--role", default="Systems_Architect", help="Role for the session")
    parser.add_argument("--description", required=True, help="Description of session work")
    parser.add_argument("--spec", default="SPEC-017", help="Spec reference ID")
    parser.add_argument("--agent", default="GEMINI", help="Agent name")
    parser.add_argument("--action", default="session_start", choices=["session_start", "session_end"], help="Action type")
    parser.add_argument("--session-id", help="Session ID (required for session_end)")
    
    args = parser.parse_args()
    
    logger = ADSLogger("_cortex/ads/events.jsonl")
    
    if args.action == "session_start":
        sid = args.session_id or f"sess_{datetime.datetime.now().strftime(\"%Y%m%d_%H%M%S\")}_{uuid.uuid4().hex[:4]}"
    else:
        sid = args.session_id or os.environ.get("ADT_SESSION_ID", "unknown")
        
    event = {
        "event_id": ADSEventSchema.generate_id(args.action),
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat().replace(\"+00:00\", \"Z\"),
        "agent": args.agent,
        "role": args.role,
        "action_type": args.action,
        "description": args.description,
        "spec_ref": args.spec,
        "authorized": True,
        "tier": 3,
        "session_id": sid
    }
    
    logger.log(event)
    print(f"Logged {args.action}: {event[\"event_id\"]} (Session: {sid})")

if __name__ == \"__main__\":
    main()
