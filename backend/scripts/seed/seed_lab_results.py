#!/usr/bin/env python
"""
seed_lab_results.py — generate LOINC lab results for existing encounters.
=========================================================================
Streams encounters from the DB and attaches LOINC-coded lab results with
realistic reference ranges and abnormal flags.

    python scripts/seed/seed_lab_results.py --scale prod

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
        await P.regenerate_child(conn, "lab_results", SCALES[scale_name])
        await conn.execute("ANALYZE lab_results")
    finally:
        await conn.close()


if __name__ == "__main__":
    args = scale_arg(__doc__)
    asyncio.run(run(args.scale))
