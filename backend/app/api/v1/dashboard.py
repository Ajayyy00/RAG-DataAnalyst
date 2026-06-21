"""Dashboard generation API routes."""

import structlog
from fastapi import APIRouter

from app.dependencies import CurrentUser, DbSession, RedisClient
from app.schemas.dashboard import DashboardGenerateRequest, DashboardResponse
from app.services.dashboard_generation_engine import DashboardGenerationEngine

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post(
    "/generate",
    response_model=DashboardResponse,
    summary="Generate a multi-panel dashboard from a natural language request",
)
async def generate_dashboard(
    request: DashboardGenerateRequest,
    current_user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
) -> DashboardResponse:
    """
    Converts a natural language request into a fully-rendered multi-panel dashboard.

    Pipeline: NL → Query Planning → Parallel SQL Execution → Chart Selection
             → Layout Assignment → Executive Summary
    """
    engine = DashboardGenerationEngine()
    dashboard = await engine.generate(
        request=request.request,
        db=db,
        redis=redis,
        user_role=getattr(current_user.role, "value", current_user.role),
    )
    logger.info(
        "Dashboard API response",
        panels=len(dashboard.panels),
        user_id=str(current_user.id),
    )
    return dashboard
