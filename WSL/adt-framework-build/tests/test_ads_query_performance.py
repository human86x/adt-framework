import os
import json
import pytest
from adt_core.ads.query import ADSQuery

def test_tail_events(tmp_path):
    ads_file = tmp_path / "events.jsonl"
    for i in range(10):
        with open(ads_file, "a") as f:
            f.write(json.dumps({"id": i, "msg": f"event {i}"}) + "\n")
    query = ADSQuery(str(ads_file))
    last_3 = query.get_all_events(limit=3)
    assert len(last_3) == 3
    assert last_3[0]["id"] == 7
    assert last_3[2]["id"] == 9
    all_events = query.get_all_events(limit=20)
    assert len(all_events) == 10
    assert all_events[0]["id"] == 0

def test_pagination(tmp_path):
    ads_file = tmp_path / "events.jsonl"
    for i in range(10):
        with open(ads_file, "a") as f:
            f.write(json.dumps({"id": i}) + "\n")
    query = ADSQuery(str(ads_file))
    page = query.get_all_events(limit=2, offset=5)
    assert len(page) == 2
    assert page[0]["id"] == 5
    assert page[1]["id"] == 6
