"""Authentication routes: register, login, refresh, me, change-password."""

from fastapi import APIRouter, Form, status

from app.dependencies import CurrentUser, DbSession
from app.schemas.auth import (
    ChangePasswordRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(data: UserRegisterRequest, db: DbSession) -> UserResponse:
    service = AuthService(db)
    user = await service.register_user(data)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive JWT tokens",
)
async def login(
    db: DbSession,
    username: str = Form(...),
    password: str = Form(...),
) -> TokenResponse:
    service = AuthService(db)
    return await service.authenticate_user(username, password)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange a refresh token for a new access token",
)
async def refresh_token(data: RefreshTokenRequest, db: DbSession) -> TokenResponse:
    service = AuthService(db)
    return await service.refresh_access_token(data.refresh_token)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
async def get_me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change current user password",
)
async def change_password(
    data: ChangePasswordRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    service = AuthService(db)
    await service.change_password(current_user, data.current_password, data.new_password)
