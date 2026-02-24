import os
import pytest
from adt_core.ads.logger import ADSLogger
from adt_core.ads.schema import ADSEventSchema
from adt_core.ads.integrity import ADSIntegrity

@pytest.fixture
def temp_ads(tmp_path):
    ads_path = tmp_path / "events.jsonl"
    return str(ads_path)

def test_logger_and_integrity(temp_ads):
    logger = ADSLogger(temp_ads)
    
    event1 = ADSEventSchema.create_event(
        event_id="evt1",
        agent="TEST",
        role="tester",
        action_type="start",
        description="Test start",
        spec_ref="SPEC-001"
    )
    logger.log(event1)
    
    event2 = ADSEventSchema.create_event(
        event_id="evt2",
        agent="TEST",
        role="tester",
        action_type="end",
        description="Test end",
        spec_ref="SPEC-001"
    )
    logger.log(event2)
    
    is_valid, errors = ADSIntegrity.verify_chain(temp_ads)
    assert is_valid
    assert not errors

def test_broken_integrity(temp_ads):
    logger = ADSLogger(temp_ads)
    event1 = ADSEventSchema.create_event(
        event_id="evt1", agent="TEST", role="tester", 
        action_type="start", description="Test", spec_ref="SPEC-001"
    )
    logger.log(event1)
    
    # Manually corrupt the file
    with open(temp_ads, "a") as f:
        f.write('{"corrupt": "data"}\n')
        
    is_valid, errors = ADSIntegrity.verify_chain(temp_ads)
    assert not is_valid
    assert len(errors) > 0
