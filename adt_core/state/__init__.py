"""REQ-125: state-resilience helpers.

Load-bearing JSON state files (tasks.json, config/intent_index.json,
config/specs.json, sovereign_requests.json, project registries, etc.) must
never fail silently on corruption. This package exports:

- ``StateCorruptionError`` -- raised by ``safe_json_load`` on JSONDecodeError.
- ``safe_json_load(path)`` -- validated read that raises on corruption.
- ``safe_json_write(path, obj)`` -- backup-then-write with rotation.
- ``run_startup_fsck(paths)`` -- validate a list of load-bearing files.

See ``_cortex/requests.md`` REQ-125 for full context (2026-08-06
solar_system_1786032782 incident: workers narrated success on POSTs that
actually 500'd because the framework's own tasks.json had lurking syntax
corruption and the endpoint fell back to it when ``?project=`` was omitted).
"""
from adt_core.state.safe_load import (  # noqa: F401
    StateCorruptionError,
    safe_json_load,
    validate_json_file,
    run_startup_fsck,
)
from adt_core.state.safe_write import (  # noqa: F401
    safe_json_write,
    prune_backups,
    list_backups,
    restore_latest_backup,
)
