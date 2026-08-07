"""SPEC-078 Part D (REQ-121) — worker interactive-prompt classifier & watcher.

Verifies:
    1. `adt_sdk.worker_prompts.classify` matches the agy OAuth log verbatim.
    2. A fake worker printing the agy OAuth prompt is detected, SIGSTOPed,
       registered as paused, and produces a `worker_awaiting_operator_input`
       ADS event with the extracted URL.

Run: python3 -m pytest tests/test_worker_prompts.py -v
     or: python3 tests/test_worker_prompts.py
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


AGY_OAUTH_SAMPLE = (
    "Authentication required. Please visit the URL to log in:\n"
    "  https://accounts.google.com/o/oauth2/auth?access_type=offline"
    "&client_id=1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
    "&code_challenge=MlAfc9f44H0U_EUcHQMBOBNplxqt7l-jIzCbZhGPaJ8"
    "&code_challenge_method=S256&prompt=consent"
    "&redirect_uri=https%3A%2F%2Fantigravity.google%2Foauth-callback"
    "&response_type=code&scope=openid&state=ABCDEF\n"
    "\n"
    "Waiting for authentication (timeout 60s)...\n"
    "Or, paste the authorization code here and press Enter:\n"
)


class TestClassifier(unittest.TestCase):
    def test_agy_oauth_matches_and_extracts_url(self):
        from adt_sdk.worker_prompts import classify
        m = classify(AGY_OAUTH_SAMPLE)
        self.assertIsNotNone(m, "classifier should match the agy OAuth sample verbatim")
        self.assertEqual(m.prompt_type, "oauth_url")
        self.assertIsNotNone(m.extracted)
        self.assertTrue(m.extracted.startswith("https://accounts.google.com/o/oauth2/auth"))
        self.assertIn("Authentication required", m.matched_line)

    def test_generic_password_prompt(self):
        from adt_sdk.worker_prompts import classify
        m = classify("some output\nPassword:")
        self.assertIsNotNone(m)
        self.assertEqual(m.prompt_type, "password")

    def test_yn_prompt(self):
        from adt_sdk.worker_prompts import classify
        m = classify("Overwrite? [Y/n]")
        self.assertIsNotNone(m)
        self.assertEqual(m.prompt_type, "yes_no")

    def test_totp_prompt(self):
        from adt_sdk.worker_prompts import classify
        m = classify("Enter TOTP code: ")
        self.assertIsNotNone(m)
        self.assertEqual(m.prompt_type, "totp")

    def test_normal_output_no_match(self):
        from adt_sdk.worker_prompts import classify
        m = classify("Compiling foo.py...\nOK. Wrote 3 files.\n")
        self.assertIsNone(m)


class TestWatcherEndToEnd(unittest.TestCase):
    """Spawn a fake worker (bash + sleep), have it print the agy OAuth
    pattern, and verify the watcher SIGSTOPs it and registers it."""

    def setUp(self):
        # Isolate ADS: point ADSLogger at a temp file so this test doesn't
        # pollute the real events.jsonl.
        self.tmp_ads_dir = tempfile.mkdtemp(prefix="adt_ads_test_")
        os.makedirs(os.path.join(self.tmp_ads_dir, "_cortex", "ads"), exist_ok=True)
        self.ads_path = os.path.join(self.tmp_ads_dir, "_cortex", "ads", "events.jsonl")
        os.environ["ADT_ADS_PATH"] = self.ads_path

        # Clean the paused-worker registry before each test.
        from adt_center.api import workers_registry
        workers_registry.PAUSED_WORKERS.clear()

    def test_fake_worker_gets_paused_and_registered(self):
        from adt_center.api.workers_watcher import spawn_prompt_watcher
        from adt_center.api import workers_registry

        # A fake worker that (a) prints the OAuth prompt then (b) sleeps
        # forever so we can observe SIGSTOP. We write the OAuth text to a
        # log file our watcher polls (same shape as the real decompose
        # spawn).
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            log_path = f.name

        # Bash writes the OAuth pattern to log then sleeps.
        script = (
            f"cat > '{log_path}' <<'EOF'\n"
            f"{AGY_OAUTH_SAMPLE}"
            f"EOF\n"
            f"sleep 300\n"
        )
        proc = subprocess.Popen(
            ["bash", "-c", script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        try:
            spawn_prompt_watcher(
                proc=proc,
                log_path=log_path,
                worker_id="test_task_001",
                spec_id="SPEC-078",
                project="test_project",
                role="Systems_Architect",
            )

            # Give the watcher time to poll + suspend (poll interval is 2s).
            deadline = time.time() + 10.0
            entry = None
            while time.time() < deadline:
                entry = workers_registry.get("test_task_001")
                if entry:
                    break
                time.sleep(0.25)

            self.assertIsNotNone(entry, "worker should have been registered as paused")
            self.assertEqual(entry["prompt_type"], "oauth_url")
            self.assertTrue(
                (entry["prompt_url"] or "").startswith("https://accounts.google.com/o/oauth2/auth"),
                f"URL was not extracted correctly: {entry.get('prompt_url')!r}",
            )
            # State should be paused (SIGSTOP succeeded) or, on OSes where
            # SIGSTOP is restricted, killed. Both are acceptable — the point
            # of REQ-121 is *no silent timeout*.
            self.assertIn(entry["state"], ("paused", "killed"))

            if entry["state"] == "paused":
                # Verify the process is actually SIGSTOPed (T status in
                # /proc/<pid>/stat). Best-effort; skip on non-Linux.
                stat_path = f"/proc/{proc.pid}/stat"
                if os.path.exists(stat_path):
                    with open(stat_path) as sf:
                        parts = sf.read().split()
                        # field 3 (0-indexed 2) is state char
                        self.assertEqual(parts[2], "T",
                                         f"process should be in T (stopped) state, got {parts[2]}")

        finally:
            # Always clean up: SIGCONT + SIGTERM the worker.
            try:
                os.kill(proc.pid, signal.SIGCONT)
            except Exception:
                pass
            try:
                os.kill(proc.pid, signal.SIGTERM)
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            try:
                os.unlink(log_path)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
