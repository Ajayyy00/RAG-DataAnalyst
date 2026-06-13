"""Authentication and user management service."""

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_refresh_token,
)
from app.db.models.user import User
from app.schemas.auth import TokenResponse, UserRegisterRequest

logger = structlog.get_logger(__name__)


class AuthService:
    """Handles user registration, login, and token lifecycle."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register_user(
        self, data: UserRegisterRequest, role: str = "analyst"
    ) -> User:
        """Create a new user; raises ConflictError if email/username already taken."""
        # Check for duplicates
        existing = await self.db.execute(
            select(User).where(
                (User.email == data.email) | (User.username == data.username)
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError("Email or username already registered")

        user = User(
            email=data.email,
            username=data.username,
            hashed_password=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            role=role,
        )
        self.db.add(user)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ConflictError("Registration failed due to a data conflict") from exc

        logger.info("User registered", user_id=str(user.id), email=user.email)
        return user

    async def authenticate_user(
        self, email: str, password: str
    ) -> TokenResponse:
        """Verify credentials and return access + refresh tokens."""
        result = await self.db.execute(
            select(User).where(User.email == email, User.is_active.is_(True))
        )
        user: Optional[User] = result.scalar_one_or_none()

        if not user or not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")

        # Update last login timestamp
        await self.db.execute(
            update(User)
            .where(User.id == user.id)
            .values(last_login_at=datetime.now(timezone.utc))
        )

        token_data = {"sub": str(user.id), "role": user.role.value if hasattr(user.role, "value") else user.role, "email": user.email}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        logger.info("User authenticated", user_id=str(user.id))
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=3600,
        )

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """Issue a new access token from a valid refresh token."""
        payload = verify_refresh_token(refresh_token)
        if not payload:
            raise AuthenticationError("Invalid or expired refresh token")

        result = await self.db.execute(
            select(User).where(
                User.id == payload["sub"], User.is_active.is_(True)
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            raise AuthenticationError("User not found")

        token_data = {"sub": str(user.id), "role": user.role, "email": user.email}
        new_access = create_access_token(token_data)
        new_refresh = create_refresh_token(token_data)

        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=3600,
        )

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> None:
        """Change a user's password after verifying the current one."""
        if not verify_password(current_password, user.hashed_password):
            raise AuthenticationError("Current password is incorrect")

        await self.db.execute(
            update(User)
            .where(User.id == user.id)
            .values(hashed_password=hash_password(new_password))
        )
        logger.info("Password changed", user_id=str(user.id))

    async def get_user_by_id(self, user_id: uuid.UUID) -> User:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundError("User")
        return user
