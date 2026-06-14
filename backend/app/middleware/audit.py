import time
import uuid

import structlog
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.security import verify_token
from app.db.models.audit import AuditLog
from app.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()

        # Determine User ID from token if present (since this runs before Dependencies)
        user_id = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                payload = verify_token(token)
                if payload and "sub" in payload:
                    user_id = uuid.UUID(payload["sub"])
            except Exception:
                pass  # Ignore invalid tokens here, Auth dependency will catch it

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000

        # Log asynchronously in a fire-and-forget manner to avoid slowing down the response
        # Actually in FastAPI middleware we can just write it synchronously before returning,
        # but using an async session.
        if request.url.path.startswith("/api/"):
            try:
                async with AsyncSessionLocal() as db:
                    audit_entry = AuditLog(
                        user_id=user_id,
                        endpoint=request.url.path,
                        method=request.method,
                        status_code=response.status_code,
                        ip_address=request.client.host if request.client else None,
                        duration_ms=duration_ms,
                    )
                    db.add(audit_entry)
                    await db.commit()
            except Exception as e:
                logger.error("Failed to write audit log", error=str(e))

        return response
