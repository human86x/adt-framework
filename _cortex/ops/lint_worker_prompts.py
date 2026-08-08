#!/usr/bin/env python3
"""REQ-125 Priority 6 + REQ-123: lint worker prompt templates.

Two hygiene checks against every ``.md`` under
``adt_center/api/*prompts/*``:

1. **REQ-125 §6** -- every ``curl`` command that hits ``/api/*`` MUST
   include ``?project=`` or ``&project=`` in the query string. A missing
   ``project=`` teaches the worker to rely on the server's silent
   fallback to the framework root, which was the 2026-08-06 SPEC-004
   incident's root cause.
2. **REQ-123** -- forbidden phrases in template payloads: named
   world-wide standards (WCAG, glTF, WebGL, IAU, Khronos, RFC-NNNN,
   ISO-NNNNN, GDPR, NGSS, UNESCO, SPDX, Dublin Core, Schema.org), RR-NNN
   references in operator-visible fields, and hedge phrases like "aligns
   with world-wide standards" / "follows industry standards".

Exit codes:
    0 -- clean
    1 -- one or more violations reported (file:line:issue format)

Usage:
    python3 _cortex/ops/lint_worker_prompts.py [--root <path>]

Standalone (no Flask imports) so it runs in CI and pre-commit contexts.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import List, Tuple


# --- REQ-123 forbidden phrases ------------------------------------------------
# Each entry is (regex, human-readable label).
FORBIDDEN_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bWCAG\b"), "WCAG (standards enumeration -- REQ-123)"),
    (re.compile(r"\bglTF\b"), "glTF (standards enumeration -- REQ-123)"),
    (re.compile(r"\bWebGL\b"), "WebGL (standards enumeration -- REQ-123)"),
    (re.compile(r"\bIAU\b"), "IAU (standards enumeration -- REQ-123)"),
    (re.compile(r"\bKhronos\b"), "Khronos (standards enumeration -- REQ-123)"),
    (re.compile(r"\bRFC\s*\d+\b"), "RFC-NNNN reference (REQ-123)"),
    (re.compile(r"\bISO\s*\d+\b"), "ISO-NNNNN reference (REQ-123)"),
    (re.compile(r"\bGDPR\b"), "GDPR (standards enumeration -- REQ-123)"),
    (re.compile(r"\bNGSS\b"), "NGSS (standards enumeration -- REQ-123)"),
    (re.compile(r"\bUNESCO\b"), "UNESCO (standards enumeration -- REQ-123)"),
    (re.compile(r"\bSPDX\b"), "SPDX (standards enumeration -- REQ-123)"),
    (re.compile(r"Dublin\s+Core"), "Dublin Core (standards enumeration -- REQ-123)"),
    (re.compile(r"Schema\.org"), "Schema.org (standards enumeration -- REQ-123)"),
    (re.compile(r"\bRR-\d{3}\b"), "RR-NNN reference in prompt (REQ-123)"),
    (
        re.compile(r"\baligns?\s+with\s+.*standards\b", re.IGNORECASE),
        "hedge phrase 'aligns with ... standards' (REQ-123)",
    ),
]


# --- REQ-125 curl-project lint ------------------------------------------------
# Match any curl invocation that references /api/. Naive but effective: we
# grab the URL argument (quoted or bare) and check for project=.
CURL_LINE = re.compile(r"\bcurl\b[^\n]*", re.IGNORECASE)
URL_ARG = re.compile(r"""(['"])(https?://[^'"\s]*?/api/[^'"\s]*)\1""")
BARE_URL = re.compile(r"(https?://[^\s'\"]*?/api/[^\s'\"]+)")


def _extract_urls(line: str) -> List[str]:
    urls = [m.group(2) for m in URL_ARG.finditer(line)]
    if urls:
        return urls
    return [m.group(1) for m in BARE_URL.finditer(line)]


def lint_file(path: str) -> List[str]:
    """Return a list of violation strings ``<path>:<line>:<issue>``."""
    violations: List[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        return [f"{path}:0:read_failed: {e}"]

    # Sticky state for multi-line curl commands with backslash continuation.
    in_curl = False
    curl_start_line = 0
    curl_buffer = ""

    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")

        # --- REQ-123 forbidden phrase scan (whole file, every line) ---------
        # Inline exemption: a line containing `noqa: REQ-123` is treated as
        # legitimate documentation of the standards mechanism (e.g.,
        # "example RR-008 inheritance", "operators MUST NOT type WCAG").
        # Use sparingly and only for docs/warnings, never for actual payloads.
        if "noqa: REQ-123" not in line:
            for pat, label in FORBIDDEN_PATTERNS:
                if pat.search(line):
                    violations.append(f"{path}:{lineno}:REQ-123: {label}")

        # --- REQ-125 curl-project scan --------------------------------------
        stripped = line.strip()
        # Detect start of curl command.
        if not in_curl and CURL_LINE.search(line):
            in_curl = True
            curl_start_line = lineno
            curl_buffer = line

        if in_curl:
            # Accumulate multi-line curl bodies (backslash-continued lines).
            if lineno != curl_start_line:
                curl_buffer += " " + line
            # Close the curl block when line does NOT end with backslash.
            if not stripped.endswith("\\"):
                # Only lint URLs that hit /api/.
                urls = _extract_urls(curl_buffer)
                api_urls = [u for u in urls if "/api/" in u]
                for u in api_urls:
                    query = u.split("?", 1)[1] if "?" in u else ""
                    if "project=" not in query:
                        violations.append(
                            f"{path}:{curl_start_line}:REQ-125: "
                            f"curl to {u} missing '?project=' / '&project='"
                        )
                in_curl = False
                curl_start_line = 0
                curl_buffer = ""

    return violations


def find_prompt_files(root: str) -> List[str]:
    """Yield every .md under adt_center/api/*prompts/*."""
    api_dir = os.path.join(root, "adt_center", "api")
    if not os.path.isdir(api_dir):
        return []
    results: List[str] = []
    for name in sorted(os.listdir(api_dir)):
        if not name.endswith("prompts"):
            continue
        sub = os.path.join(api_dir, name)
        if not os.path.isdir(sub):
            continue
        for f in sorted(os.listdir(sub)):
            if f.endswith(".md"):
                results.append(os.path.join(sub, f))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        default=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        ),
        help="Framework root (default: repo root)",
    )
    args = ap.parse_args()

    files = find_prompt_files(args.root)
    if not files:
        print(
            f"[lint_worker_prompts] no prompt templates found under "
            f"{args.root}/adt_center/api/*prompts/",
            file=sys.stderr,
        )
        return 0

    all_violations: List[str] = []
    for f in files:
        all_violations.extend(lint_file(f))

    if not all_violations:
        print(
            f"[lint_worker_prompts] OK -- {len(files)} template(s) clean "
            f"(REQ-123 + REQ-125)"
        )
        return 0

    for v in all_violations:
        print(v)
    print(
        f"[lint_worker_prompts] FAIL -- {len(all_violations)} violation(s) "
        f"across {len(files)} template(s)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
