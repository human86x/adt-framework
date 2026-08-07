"""
SPEC-078 Part D (REQ-121): Worker Interactive Prompt Classifier

Purpose:
    When a worker subprocess (typically agy / gemini / claude CLIs) blocks
    on an interactive prompt (OAuth URL, password, [Y/n], TOTP), our
    orchestrator today would silently wait for its own timeout. That is
    the exact governance failure REQ-121 fixes. This module gives us a
    lightweight, dependency-free regex classifier that inspects the tail
    of a worker's log and returns a structured verdict.

    On a positive match, the caller (e.g. build_executor._spawn_stall_monitor
    or the /decompose worker watcher) should:
        1. SUSPEND the worker via SIGSTOP (preferred) OR
           terminate cleanly if suspend isn't safe for the process tree.
        2. Emit a `worker_awaiting_operator_input` ADS event with the
           extracted prompt text/URL.
        3. Register the paused worker in an in-memory registry so the
           Console can surface it and the operator can Resume / Cancel.

    Kept as a pure-Python module with no framework imports so it can be
    unit-tested in isolation (see tests/test_worker_prompts.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


# --- Signature table ----------------------------------------------------------
# Ordering matters ONLY for reporting: the first match in the list wins when
# multiple signatures could apply. Keep the most specific patterns first.

@dataclass(frozen=True)
class PromptSignature:
    name: str                # short id, e.g. "agy_oauth"
    prompt_type: str         # semantic category shown in UI
    marker_regex: re.Pattern # anchor phrase that triggers a match
    extract_regex: Optional[re.Pattern]  # captures the URL / prompt text (group 0 used)
    human_hint: str          # 1-line operator instruction


SIGNATURES: List[PromptSignature] = [
    # -- agy (Antigravity) OAuth flow --------------------------------------
    # Log line ex:
    #   Authentication required. Please visit the URL to log in:
    #     https://accounts.google.com/o/oauth2/auth?...
    #   Waiting for authentication (timeout 60s)...
    PromptSignature(
        name="agy_oauth",
        prompt_type="oauth_url",
        marker_regex=re.compile(
            r"Authentication required\. Please visit the URL", re.IGNORECASE
        ),
        extract_regex=re.compile(
            r"https://accounts\.google\.com/o/oauth2/auth\S+"
        ),
        human_hint="Open the URL, complete Google sign-in, then click Resume.",
    ),
    # Generic 'Waiting for authentication' line — agy prints this even when
    # the URL line has already scrolled out of our tail window.
    PromptSignature(
        name="agy_oauth_waiting",
        prompt_type="oauth_wait",
        marker_regex=re.compile(
            r"Waiting for authentication \(timeout \d+s?\)", re.IGNORECASE
        ),
        extract_regex=re.compile(
            r"https://accounts\.google\.com/o/oauth2/auth\S+"
        ),
        human_hint="Worker is waiting for auth. Re-auth agy in a terminal, then Resume.",
    ),
    # -- TOTP / 2FA prompts ------------------------------------------------
    PromptSignature(
        name="totp_code",
        prompt_type="totp",
        marker_regex=re.compile(
            r"Enter (?:verification|TOTP|2FA|MFA) code", re.IGNORECASE
        ),
        extract_regex=None,
        human_hint="Enter the current 6-digit code from your authenticator app.",
    ),
    # -- Generic Y/N confirmations -----------------------------------------
    PromptSignature(
        name="yes_no_capital_y",
        prompt_type="yes_no",
        marker_regex=re.compile(r"\[Y/n\]\s*$", re.MULTILINE),
        extract_regex=None,
        human_hint="Worker is waiting for a Yes/No confirmation.",
    ),
    PromptSignature(
        name="yes_no_capital_n",
        prompt_type="yes_no",
        marker_regex=re.compile(r"\[y/N\]\s*$", re.MULTILINE),
        extract_regex=None,
        human_hint="Worker is waiting for a Yes/No confirmation.",
    ),
    # -- Password / passphrase prompts -------------------------------------
    PromptSignature(
        name="password_prompt",
        prompt_type="password",
        marker_regex=re.compile(r"(?im)(?:^|\s)(?:Password|Passphrase):\s*$"),
        extract_regex=None,
        human_hint="Worker requires a password. Provide credentials, then Resume.",
    ),
    # -- 'paste the authorization code' (agy secondary prompt) -------------
    PromptSignature(
        name="agy_paste_auth_code",
        prompt_type="paste_code",
        marker_regex=re.compile(
            r"paste the authorization code here and press Enter", re.IGNORECASE
        ),
        extract_regex=None,
        human_hint="Complete OAuth in your browser first, then Resume.",
    ),
]


@dataclass(frozen=True)
class PromptMatch:
    name: str
    prompt_type: str
    extracted: Optional[str]   # URL or captured text, if any
    hint: str
    matched_line: str          # the exact line that triggered the match


def classify(text: str) -> Optional[PromptMatch]:
    """Scan `text` (typically the last few KB of a worker log) for any
    known interactive-prompt signature. Returns the first match (in
    SIGNATURES order) or None.

    The classifier is deliberately conservative: it looks for stable
    anchor phrases printed by the CLI tools themselves, not arbitrary
    heuristics that might false-positive on regular worker output.
    """
    if not text:
        return None
    for sig in SIGNATURES:
        m = sig.marker_regex.search(text)
        if not m:
            continue
        # Try to extract a URL/token from the whole tail (not just the
        # matched line) because CLIs often print the URL on a separate
        # line than the marker phrase.
        extracted = None
        if sig.extract_regex is not None:
            em = sig.extract_regex.search(text)
            if em:
                extracted = em.group(0)
        # Locate the line for reporting.
        start = text.rfind("\n", 0, m.start()) + 1
        end = text.find("\n", m.end())
        if end == -1:
            end = len(text)
        line = text[start:end].strip()
        return PromptMatch(
            name=sig.name,
            prompt_type=sig.prompt_type,
            extracted=extracted,
            hint=sig.human_hint,
            matched_line=line,
        )
    return None


def classify_log_tail(log_path: str, tail_bytes: int = 4000) -> Optional[PromptMatch]:
    """Convenience: read the last `tail_bytes` of a worker log and classify.

    Returns None if the file is empty, missing, or contains no known
    prompt signature.
    """
    import os
    if not log_path or not os.path.exists(log_path):
        return None
    try:
        size = os.path.getsize(log_path)
        with open(log_path, "rb") as f:
            f.seek(max(0, size - tail_bytes))
            data = f.read()
        return classify(data.decode("utf-8", errors="replace"))
    except OSError:
        return None
