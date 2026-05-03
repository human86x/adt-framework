import sys
import os
sys.path.append(os.getcwd())
from adt_core.ads.logger import ADSLogger
from adt_core.ads.schema import ADSEventSchema
def main():
    logger = ADSLogger('_cortex/ads/events.jsonl')
    event_id = ADSEventSchema.generate_id('session_st')
    event = ADSEventSchema.create_event(
        event_id=event_id,
        agent='GEMINI',
        role='Backend_Engineer',
        action_type='session_start',
        description='Backend Engineer session started. Initializing SPEC-046 Standards Governance Layer.',
        spec_ref='SPEC-046',
        authorized=True,
        tier=3
    )
    logger.log(event)
    print(f'Logged session start: {event_id}')
if __name__ == '__main__':
    main()