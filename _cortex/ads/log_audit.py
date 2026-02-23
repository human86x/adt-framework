import os
import sys
from datetime import datetime, timezone

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from adt_core.ads.logger import ADSLogger
from adt_core.ads.schema import ADSEventSchema

def log_audit_events():
    ads_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "events.jsonl"))
    logger = ADSLogger(ads_path)
    
    # 1. Log ADS Healing
    healing_event = ADSEventSchema.create_event(
        event_id=ADSEventSchema.generate_id("healing"),
        agent="GEMINI",
        role="Overseer",
        action_type="ads_healing",
        description="ADS hash chain was found broken and has been healed using heal_ads.py. Integrity verified.",
        spec_ref="SPEC-020",
        authorized=True,
        tier=1
    )
    logger.log(healing_event)
    print(f"Logged healing event: {healing_event['event_id']}")
    
    # 2. Log Break-Glass Audit
    audit_event = ADSEventSchema.create_event(
        event_id=ADSEventSchema.generate_id("audit"),
        agent="GEMINI",
        role="Overseer",
        action_type="break_glass_audit",
        description="Audit of break-glass event evt_1771413109_4820. Status: VERIFIED. Change to config/jurisdictions.json (adding sample_projects/) is minimal and justified by SPEC-031.",
        spec_ref="SPEC-020",
        authorized=True,
        tier=1
    )
    logger.log(audit_event)
    print(f"Logged audit event: {audit_event['event_id']}")

if __name__ == "__main__":
    log_audit_events()
