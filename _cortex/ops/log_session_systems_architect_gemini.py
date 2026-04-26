import os
import sys
from datetime import datetime, timezone
from adt_core.ads.logger import ADSLogger
from adt_core.ads.schema import ADSEventSchema

def log_session_start():
    ads_path = os.path.join('_cortex', 'ads', 'events.jsonl')
    logger = ADSLogger(ads_path)
    
    # Generate a unique session ID
    session_id = f'sess_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}_sa_gemini'
    
    event_id = ADSEventSchema.generate_id('session_start')
    description = 'Systems Architect session started. Initializing SPEC-044 Phase A (DTTP->DTCP rename) and SPEC-043 Forge Protocol.'
    
    event = ADSEventSchema.create_event(
        event_id=event_id,
        agent='GEMINI',
        role='Systems_Architect',
        action_type='session_start',
        description=description,
        spec_ref='SPEC-017',
        authorized=True,
        tier=3,
        session_id=session_id,
        action_data={
            'active_specs': ['SPEC-043', 'SPEC-044'],
            'pending_tasks': ['task_227', 'task_230', 'task_231', 'task_232', 'task_233', 'task_240']
        }
    )
    
    logger.log(event)
    print(f'Logged session_start: {event_id} (Session: {session_id})')

if __name__ == '__main__':
    log_session_start()
