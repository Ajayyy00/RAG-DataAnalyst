#!/usr/bin/env python
"""
Healthcare Copilot — full Supabase data pipeline orchestrator.
==============================================================
Generates the complete dataset (reference + patients + encounters + all child
tables + readmissions) at a chosen scale, using chunked binary COPY.

Usage:
    python -m scripts.seed.seed_all --scale small   [--truncate] [--users]
    python -m scripts.seed.seed_all --scale prod    --truncate --users

Scales: demo | small | medium | prod   (see seeding/scales.py)
Targets the database resolved from your .env (SUPABASE_DB_URL or POSTGRES_*).
Run AFTER `alembic upgrade head` (schema + RLS must already exist).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from seeding import pipeline as P
from seeding.bulk import connect, truncate_all
from seeding.scales import DEFAULT_SCALE, SCALES

DEMO_USERS = [
    ("admin@healthcopilot.internal", "admin", "Admin", "User", "admin", "Admin1234!"),
    (
        "analyst@healthcopilot.internal",
        "analyst",
        "Data",
        "Analyst",
        "analyst",
        "Analyst1234!",
    ),
    (
        "clinician@healthcopilot.internal",
        "clinician",
        "Jane",
        "Doe",
        "doctor",
        "Clinician1234!",
    ),
]


async def seed_users(conn) -> int:
    """Create demo login users if absent (idempotent). Names stored plaintext —
    the EncryptedString column reads legacy plaintext transparently."""
    from passlib.context import CryptContext

    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    created = 0
    for email, username, first, last, role, password in DEMO_USERS:
        exists = await conn.fetchval("SELECT 1 FROM users WHERE email = $1", email)
        if exists:
            continue
        await conn.execute(
            """
            INSERT INTO users (id, email, username, hashed_password, first_name,
                               last_name, role, is_active, created_at, updated_at)
            VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, true, now(), now())
            """,
            email,
            username,
            pwd.hash(password),
            first,
            last,
            role,
        )
        created += 1
    print(f"  [users] {created} demo user(s) created")
    return created


async def run(scale_name: str, truncate: bool, users: bool, readmissions: bool) -> None:
    scale = SCALES[scale_name]
    print("=" * 64)
    print(
        f"  Healthcare Copilot — seeding scale='{scale.name}' "
        f"(~{scale.total_rows:,} target rows)"
    )
    print("=" * 64)

    conn = await connect()
    started = time.perf_counter()
    try:
        if truncate:
            await truncate_all(conn)

        fac_ids = await P.seed_facilities(conn, scale)
        dept_ids = await P.seed_departments(conn, fac_ids)
        physician_ids = await P.seed_providers(conn, scale, dept_ids)
        patient_ids, birth_years = await P.seed_patients(conn, scale)
        counts = await P.seed_encounters(
            conn, scale, patient_ids, birth_years, physician_ids, dept_ids
        )
        readmits = await P.build_readmissions(conn) if readmissions else 0
        if users:
            await seed_users(conn)

        await conn.execute("ANALYZE")
    finally:
        await conn.close()

    elapsed = time.perf_counter() - started
    grand = (
        scale.facilities
        + len(dept_ids)
        + scale.providers
        + scale.patients
        + counts["encounters"]
        + counts["diagnoses"]
        + counts["lab_results"]
        + counts["medications"]
        + counts["procedures"]
        + counts["vital_signs"]
        + counts["claims"]
        + readmits
    )
    print("\n" + "=" * 64)
    print("  Seed complete")
    print("=" * 64)
    print(f"  facilities    {scale.facilities:>12,}")
    print(f"  departments   {len(dept_ids):>12,}")
    print(
        f"  providers     {scale.providers:>12,}   "
        f"({scale.physicians:,} physicians / {scale.nurses:,} nurses)"
    )
    print(f"  patients      {scale.patients:>12,}")
    print(f"  encounters    {counts['encounters']:>12,}")
    print(f"  diagnoses     {counts['diagnoses']:>12,}")
    print(f"  lab_results   {counts['lab_results']:>12,}")
    print(f"  medications   {counts['medications']:>12,}")
    print(f"  procedures    {counts['procedures']:>12,}")
    print(f"  vital_signs   {counts['vital_signs']:>12,}")
    print(f"  claims        {counts['claims']:>12,}")
    print(f"  readmissions  {readmits:>12,}")
    print(f"  {'-' * 30}")
    print(
        f"  TOTAL         {grand:>12,}   in {elapsed/60:.1f} min "
        f"({grand/elapsed:,.0f} rows/s)"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed the Healthcare Copilot dataset")
    ap.add_argument("--scale", choices=list(SCALES), default=DEFAULT_SCALE)
    ap.add_argument(
        "--truncate", action="store_true", help="Truncate clinical tables first"
    )
    ap.add_argument("--users", action="store_true", help="Also create demo login users")
    ap.add_argument("--no-readmissions", action="store_true")
    args = ap.parse_args()
    asyncio.run(run(args.scale, args.truncate, args.users, not args.no_readmissions))


if __name__ == "__main__":
    main()
