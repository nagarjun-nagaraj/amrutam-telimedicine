from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException, status
from app.models.models import User, UserProfile, RefreshToken, UserRole
from app.schemas.schemas import UserRegisterRequest, UserLoginRequest, TokenResponse
from app.core.security import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, decode_token, hash_token,
    generate_mfa_secret, generate_mfa_qr_code, verify_mfa_token
)
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 30


class AuthService:

    # ── Registration ───────────────────────────────────────────────────────

    async def register_user(
        self,
        db: AsyncSession,
        request: UserRegisterRequest,
        ip_address: str = "unknown"
    ) -> User:
        # Check email already exists
        result = await db.execute(
            select(User).where(User.email == request.email)
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered"
            )

        # Check phone already exists
        if request.phone:
            result = await db.execute(
                select(User).where(User.phone == request.phone)
            )
            existing_phone = result.scalar_one_or_none()
            if existing_phone:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Phone number already registered"
                )

        # Create user
        user = User(
            email=request.email,
            phone=request.phone,
            hashed_password=hash_password(request.password),
            role=request.role,
            is_active=True,
            is_verified=False,
        )
        db.add(user)
        await db.flush()

        # Create profile
        profile = UserProfile(
            user_id=user.id,
            first_name=request.first_name,
            last_name=request.last_name,
        )
        db.add(profile)
        await db.flush()

        logger.info(
            "user_registered",
            user_id=str(user.id),
            email=user.email,
            role=user.role,
            ip=ip_address
        )

        return user

    # ── Login ──────────────────────────────────────────────────────────────

    async def login(
        self,
        db: AsyncSession,
        request: UserLoginRequest,
        ip_address: str = "unknown",
        user_agent: str = "unknown"
    ) -> TokenResponse:
        # Fetch user
        result = await db.execute(
            select(User).where(User.email == request.email)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Check account lockout
        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Account locked. Try again after {user.locked_until.isoformat()}"
            )

        # Verify password
        if not verify_password(request.password, user.hashed_password):
            await self._handle_failed_login(db, user)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled"
            )

        # MFA check
        if user.mfa_enabled:
            if not request.mfa_token:
                raise HTTPException(
                    status_code=status.HTTP_200_OK,
                    detail="MFA token required"
                )
            if not verify_mfa_token(user.mfa_secret, request.mfa_token):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid MFA token"
                )

        # Reset failed attempts on success
        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(
                failed_login_attempts=0,
                locked_until=None,
                last_login=datetime.now(timezone.utc)
            )
        )

        # Generate tokens
        access_token = create_access_token(
            data={"sub": str(user.id), "role": user.role, "email": user.email}
        )
        refresh_token = create_refresh_token(
            data={"sub": str(user.id)}
        )

        # Store refresh token hash
        token_record = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(token_record)

        logger.info(
            "user_logged_in",
            user_id=str(user.id),
            ip=ip_address
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=str(user.id),
            role=user.role
        )

    # ── Refresh Token ──────────────────────────────────────────────────────

    async def refresh_access_token(
        self,
        db: AsyncSession,
        refresh_token: str
    ) -> TokenResponse:
        payload = decode_token(refresh_token)

        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        token_hash = hash_token(refresh_token)
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.is_revoked == False
            )
        )
        token_record = result.scalar_one_or_none()

        if not token_record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token not found or revoked"
            )

        if token_record.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired"
            )

        # Revoke old token (rotation)
        token_record.is_revoked = True
        await db.flush()

        # Fetch user
        result = await db.execute(
            select(User).where(User.id == payload["sub"])
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        # Issue new tokens
        access_token = create_access_token(
            data={"sub": str(user.id), "role": user.role, "email": user.email}
        )
        new_refresh_token = create_refresh_token(
            data={"sub": str(user.id)}
        )

        import uuid as uuid_lib
        new_token_record = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(new_refresh_token) + str(uuid_lib.uuid4()),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        db.add(new_token_record)

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=str(user.id),
            role=user.role
        )

    # ── MFA Setup ──────────────────────────────────────────────────────────

    async def setup_mfa(
        self,
        db: AsyncSession,
        user: User
    ) -> dict:
        if user.mfa_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MFA is already enabled"
            )

        secret = generate_mfa_secret()
        qr_code = generate_mfa_qr_code(secret, user.email)

        # Store secret temporarily (not enabled until verified)
        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(mfa_secret=secret)
        )

        return {
            "secret": secret,
            "qr_code": qr_code,
            "message": "Scan QR code with your authenticator app, then verify"
        }

    async def verify_and_enable_mfa(
        self,
        db: AsyncSession,
        user: User,
        token: str
    ) -> bool:
        if not user.mfa_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MFA setup not initiated"
            )

        if not verify_mfa_token(user.mfa_secret, token):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid MFA token"
            )

        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(mfa_enabled=True)
        )

        logger.info("mfa_enabled", user_id=str(user.id))
        return True

    # ── Logout ─────────────────────────────────────────────────────────────

    async def logout(
        self,
        db: AsyncSession,
        refresh_token: str
    ) -> bool:
        token_hash = hash_token(refresh_token)
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash
            )
        )
        token_record = result.scalar_one_or_none()

        if token_record:
            token_record.is_revoked = True

        return True

    # ── Private Helpers ────────────────────────────────────────────────────

    async def _handle_failed_login(
        self,
        db: AsyncSession,
        user: User
    ) -> None:
        new_attempts = user.failed_login_attempts + 1
        locked_until = None

        if new_attempts >= MAX_FAILED_ATTEMPTS:
            locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            logger.warning(
                "account_locked",
                user_id=str(user.id),
                attempts=new_attempts
            )

        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(
                failed_login_attempts=new_attempts,
                locked_until=locked_until
            )
        )


auth_service = AuthService()