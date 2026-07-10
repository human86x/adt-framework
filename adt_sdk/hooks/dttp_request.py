#!/usr/bin/env python3
"""
DTCP Request Hook (Shim)
DEPRECATED: Use dtcp_request.py instead.
"""
import warnings
import sys
import os

warnings.warn("dtcp_request.py is deprecated; use dtcp_request.py (SPEC-044)", DeprecationWarning, stacklevel=2)

# Ensure we can import dtcp_request
sys.path.append(os.path.dirname(__file__))
from dtcp_request import main

if __name__ == "__main__":
    main()
