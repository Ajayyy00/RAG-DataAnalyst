"""Reset admin password to known value for testing."""
import asyncio, sys
sys.path.insert(0, '.')
import structlog; structlog.configure(logger_factory=structlog.PrintLoggerFactory())
from app.db.session import AsyncSessionLocal
from app.core.security import hash_password
from sqlalchemy import text

NEW_PASSWORD = "Admin1234!"

async def reset():
    async with AsyncSessionLocal() as db:
        hashed = hash_password(NEW_PASSWORD)
        await db.execute(
            text("UPDATE users SET hashed_password = :h WHERE email = 'admin@healthcare.com'"),
            {"h": hashed}
        )
        await db.commit()
        print(f"Admin password reset to: {NEW_PASSWORD}")

asyncio.run(reset())
