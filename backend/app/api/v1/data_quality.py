from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.dependencies import get_db, get_current_user
from app.db.models.user import User, UserRole
from app.schemas.data_quality import DataQualityAnalyzeRequest, DataQualityReport
from app.services.data_quality_service import DataQualityService

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/data-quality", tags=["data-quality"])

@router.post("/analyze", response_model=DataQualityReport)
async def analyze_table_quality(
    request: DataQualityAnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyzes the quality of a given database table.
    Restricted to Admins and Analysts.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.ANALYST]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to run data quality analysis."
        )

    try:
        dq_service = DataQualityService(db)
        report = await dq_service.analyze_table(request.table_name, request.limit)
        return report
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error("Data Quality analysis failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error during analysis")
