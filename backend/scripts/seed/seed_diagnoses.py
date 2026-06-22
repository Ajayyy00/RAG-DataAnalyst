#!/usr/bin/env python
"""
seed_diagnoses.py — generate ICD-10 diagnoses for existing encounters.
======================================================================
Streams encounters from the DB (server-side cursor) and attaches age- and
prevalence-weighted ICD-10 diagnoses, concentrated on inpatient/ED encounters.

    python scripts/seed/seed_diagnoses.py --scale prod

Requires patients + encounters to already be seeded (run seed_all or
seed_patients + the encounter stage first).
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
        await P.regenerate_child(conn, "diagnoses", SCALES[scale_name])
        await conn.execute("ANALYZE diagnoses")
    finally:
        await conn.close()


if __name__ == "__main__":
    args = scale_arg(__doc__)
    asyncio.run(run(args.scale))
