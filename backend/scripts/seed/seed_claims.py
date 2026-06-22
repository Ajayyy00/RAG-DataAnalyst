#!/usr/bin/env python
"""
seed_claims.py — generate insurance claims for existing encounters.
===================================================================
Streams encounters from the DB and attaches claims (billed/allowed/paid,
payer mix, paid/denied/pending status), concentrated on billable
inpatient/ED/outpatient encounters.

    python scripts/seed/seed_claims.py --scale prod

Requires patients + encounters to already be seeded.
"""
from __future__ import annotations

import asyncio

from _common import scale_arg
from seeding import pipeline as P
from seeding.bulk import connect
from seeding.scales import SCALES


async def run(scale_name: str) -> None:
    conn = await connect()
    try:
        await P.regenerate_child(conn, "claims", SCALES[scale_name])
        await conn.execute("ANALYZE claims")
    finally:
        await conn.close()


if __name__ == "__main__":
    args = scale_arg(__doc__)
    asyncio.run(run(args.scale))
