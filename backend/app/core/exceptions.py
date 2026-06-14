"""Custom exceptions and FastAPI exception handlers."""

from typing import Any, List, Optional

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)


# ── Base Exception ────────────────────────────────────────────────────────────


class CopilotException(Exception):
    """Base exception for all Healthcare Copilot errors."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail: Optional[Any] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


# ── Domain Exceptions ─────────────────────────────────────────────────────────


class AuthenticationError(CopilotException):
    """Raised on invalid credentials or expired tokens."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, status_code=status.HTTP_401_UNAUTHORIZED)


class AuthorizationError(CopilotException):
    """Raised when a user lacks the required role/permission."""

    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message, status_code=status.HTTP_403_FORBIDDEN)


class NotFoundError(CopilotException):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(f"{resource} not found", status_code=status.HTTP_404_NOT_FOUND)


class SQLValidationError(CopilotException):
    """Raised when generated SQL fails validation checks."""

    def __init__(self, message: str, violations: Optional[List[str]] = None) -> None:
        super().__init__(message, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.violations = violations or []


class QueryExecutionError(CopilotException):
    """Raised on database query failures or timeouts."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LLMServiceError(CopilotException):
    """Raised when the LLM service is unavailable or returns an error."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


class RAGServiceError(CopilotException):
    """Raised on ChromaDB / embedding failures."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


class ConflictError(CopilotException):
    """Raised on resource conflicts (e.g. duplicate email)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=status.HTTP_409_CONFLICT)


# ── FastAPI Handler Registration ──────────────────────────────────────────────


def setup_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI application."""

    @app.exception_handler(CopilotException)
    async def copilot_exception_handler(
        request: Request, exc: CopilotException
    ) -> JSONResponse:
        logger.error(
            "Copilot exception",
            path=str(request.url),
            method=request.method,
            exception_type=exc.__class__.__name__,
            message=exc.message,
            status_code=exc.status_code,
        )
        body: dict = {
            "error": exc.__class__.__name__,
            "message": exc.message,
        }
        if exc.detail is not None:
            body["detail"] = exc.detail
        if isinstance(exc, SQLValidationError) and exc.violations:
            body["violations"] = exc.violations
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        sanitized_errors = []
        for error in errors:
            sanitized_error = dict(error)
            if "input" in sanitized_error and isinstance(
                sanitized_error["input"], bytes
            ):
                sanitized_error["input"] = sanitized_error["input"].decode(
                    "utf-8", errors="ignore"
                )
            sanitized_errors.append(sanitized_error)

        logger.warning(
            "Request validation error",
            path=str(request.url),
            errors=sanitized_errors,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "ValidationError", "detail": sanitized_errors},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception(
            "Unhandled exception",
            path=str(request.url),
            method=request.method,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "An unexpected error occurred. Please try again later.",
            },
        )
