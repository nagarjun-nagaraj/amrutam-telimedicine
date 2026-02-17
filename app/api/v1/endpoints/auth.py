from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.schemas import (
    UserRegisterRequest, UserLoginRequest, TokenResponse,
    RefreshTokenRequest, MFASetupResponse, MFAVerifyRequest,
    UserResponse
)
from app.services.auth_service import auth_service
from app.core.dependencies import get_current_active_user, get_client_ip, get_user_agent
from app.models.models import User
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    body: UserRegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user (patient, doctor, or admin)"""
    ip = get_client_ip(request)
    user = await auth_service.register_user(db, body, ip_address=ip)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: UserLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """Login with email and password. MFA token required if MFA is enabled."""
    ip = get_client_ip(request)
    ua = get_user_agent(request)
    return await auth_service.login(db, body, ip_address=ip, user_agent=ua)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """Get a new access token using a refresh token"""
    return await auth_service.refresh_access_token(db, body.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Logout and revoke refresh token"""
    await auth_service.logout(db, body.refresh_token)


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Initiate MFA setup — returns QR code to scan"""
    result = await auth_service.setup_mfa(db, current_user)
    return result


@router.post("/mfa/verify", status_code=status.HTTP_200_OK)
async def verify_mfa(
    body: MFAVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Verify MFA token and enable MFA on account"""
    await auth_service.verify_and_enable_mfa(db, current_user, body.token)
    return {"message": "MFA enabled successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_active_user)
):
    """Get current authenticated user info"""
    return current_user