import asyncio, sys
sys.path.insert(0, '.')
import structlog; structlog.configure(logger_factory=structlog.PrintLoggerFactory())
from app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def check():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("SELECT email, role, is_active FROM users LIMIT 10"))
        rows = r.fetchall()
        print("Users in DB:")
        for row in rows:
            print(" ", row)
        if not rows:
            print("  No users found!")

asyncio.run(check())
