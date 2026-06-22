#!/usr/bin/env python
"""
seed_doctors.py — seed the clinical workforce (hospitals, departments, providers).
=================================================================================
Generates facilities ("Hospitals"), their departments, and providers split into
physicians ("Doctors") and nurses, tagged via providers.provider_type.

    python scripts/seed/seed_doctors.py --scale prod

Standalone-safe: depends on no other table. Run before patients/encounters.
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
        fac_ids = await P.seed_facilities(conn, scale)
        dept_ids = await P.seed_departments(conn, fac_ids)
        await P.seed_providers(conn, scale, dept_ids)
        await conn.execute("ANALYZE providers")
        print(
            f"  Workforce seeded: {scale.facilities:,} hospitals, "
            f"{scale.physicians:,} physicians, {scale.nurses:,} nurses"
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    args = scale_arg(__doc__)
    asyncio.run(run(args.scale))
