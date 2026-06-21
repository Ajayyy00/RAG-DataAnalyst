"""Backfill / rotate PHI encryption for the users table.

Reads every user via the ORM (which decrypts legacy plaintext or old-key
ciphertext transparently) and re-saves (which re-encrypts under the CURRENT
first key). Idempotent and safe to run repeatedly.

Usage::

    python -m app.scripts.reencrypt_pii
"""

import asyncio

import structlog
from sqlalchemy import select

from app.core.encryption import encryption_enabled
from app.db.models.user import User
from app.db.session import AsyncSessionLocal

log = structlog.get_logger(__name__)


async def reencrypt_all() -> int:
    if not encryption_enabled():
        log.warning("PHI encryption disabled (no key) — nothing to do")
        return 0
    count = 0
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User))).scalars().all()
        for u in users:
            # Touch the encrypted fields so they are re-written under the
            # current key on flush. Decryption already happened on load.
            u.first_name = u.first_name
            u.last_name = u.last_name
            count += 1
        await db.commit()
    log.info("Re-encrypted PHI for users", users=count)
    return count


if __name__ == "__main__":
    asyncio.run(reencrypt_all())
