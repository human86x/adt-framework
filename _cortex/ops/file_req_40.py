
import datetime
path = '_cortex/requests.md'
with open(path, 'a') as f:
    f.write('''
---

## REQ-040: Strict Project Context Filtering in ADT Panel

**From:** DevOps_Engineer (GEMINI)
**To:** @Backend_Engineer
**Date: {now} UTC**
**Type:** ARCHITECTURAL_FIX
**Priority:** HIGH

### Description

Currently, selecting an external project (e.g., 'smart-lab') in the ADT Panel results in a mixed view where internal Forge specs/ADS events are still visible alongside project-specific items.

**Requirements:**
1. Update `adt_center/app.py` and all routes in `adt_center/api/` to strictly scope data by the `project` query parameter.
2. Ensure that when a project is selected, the internal Forge (Framework) data is hidden unless explicitly requested.
3. Verify that background API polling (ADS events, task updates) respects the active project context to prevent data leakage between project views.

### Status

**OPEN**
'''.format(now=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')))
print('REQ-040 filed successfully.')