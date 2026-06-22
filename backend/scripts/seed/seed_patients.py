#!/usr/bin/env python
"""
seed_patients.py — seed the patient population.
===============================================
Generates patients with US-representative age/gender/race/ethnicity/payer
distributions (Medicare skews 65+). Depends on no other table.

    python scripts/seed/seed_patients.py --scale prod
"""
from __future__ import annotations

import asyncio

from _common import scale_arg
from seeding import pipeline as P
from seeding.bulk import connect
from seeding.scales import SCALES


async def run(scale_name: str) -> None:
    scale = SCALES[scale_name]
    conn = await connect()
    try:
        await P.seed_patients(conn, scale)
        await conn.execute("ANALYZE patients")
        print(f"  {scale.patients:,} patients seeded")
    finally:
        await conn.close()


if __name__ == "__main__":
    args = scale_arg(__doc__)
    asyncio.run(run(args.scale))
