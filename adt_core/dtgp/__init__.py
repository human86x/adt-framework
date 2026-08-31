"""Digital Transformation Gateway Protocol (DTGP) -- External-target mediation gateway.

Sibling to DTCP. Mediates every ADT worker action whose effects extend beyond
the local filesystem: SSH, HTTP, USB-serial, firmware flash, etc.
Holds credentials, resolves multi-hop access paths, serialises access per target,
and logs every crossing to ADS.

SPEC-113.
"""
