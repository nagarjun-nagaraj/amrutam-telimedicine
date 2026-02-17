from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, cast, Date
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID
from app.db.session import get_db
from app.models.models import (
    User, Doctor, Consultation, Payment,
    ConsultationStatus, PaymentStatus, AuditLog, UserRole
)
from app.schemas.schemas import AnalyticsResponse, UserResponse, DoctorResponse
from app.core.dependencies import require_admin
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Analytics Dashboard ────────────────────────────────────────────────────

@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get platform analytics — admin only"""
    today = datetime.now(timezone.utc).date()

    # Total users
    total_users = await db.scalar(select(func.count(User.id)))

    # Total doctors
    total_doctors = await db.scalar(select(func.count(Doctor.id)))

    # Total consultations
    total_consultations = await db.scalar(select(func.count(Consultation.id)))

    # Consultations today
    consultations_today = await db.scalar(
        select(func.count(Consultation.id)).where(
            cast(Consultation.created_at, Date) == today
        )
    )

    # Revenue today
    revenue_today_result = await db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            and_(
                Payment.status == PaymentStatus.COMPLETED,
                cast(Payment.created_at, Date) == today
            )
        )
    )

    # Total revenue
    total_revenue_result = await db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.COMPLETED
        )
    )

    # Top specializations
    spec_result = await db.execute(
        select(Doctor.specialization, func.count(Doctor.id).label("count"))
        .group_by(Doctor.specialization)
        .order_by(func.count(Doctor.id).desc())
        .limit(5)
    )
    top_specializations = [
        {"specialization": row[0], "count": row[1]}
        for row in spec_result.fetchall()
    ]

    # Consultation status breakdown
    status_result = await db.execute(
        select(Consultation.status, func.count(Consultation.id).label("count"))
        .group_by(Consultation.status)
    )
    status_breakdown = {
        row[0].value: row[1]
        for row in status_result.fetchall()
    }

    return AnalyticsResponse(
        total_users=total_users or 0,
        total_doctors=total_doctors or 0,
        total_consultations=total_consultations or 0,
        consultations_today=consultations_today or 0,
        revenue_today=float(revenue_today_result or 0),
        revenue_total=float(total_revenue_result or 0),
        top_specializations=top_specializations,
        consultation_status_breakdown=status_breakdown
    )


# ── User Management ────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserResponse])
async def list_users(
    role: Optional[UserRole] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """List all users with optional filters — admin only"""
    filters = []
    if role:
        filters.append(User.role == role)
    if is_active is not None:
        filters.append(User.is_active == is_active)

    result = await db.execute(
        select(User)
        .where(and_(*filters) if filters else True)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .order_by(User.created_at.desc())
    )
    return result.scalars().all()


@router.patch("/users/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Activate a user account — admin only"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = True
    await db.flush()
    logger.info("user_activated", user_id=str(user_id), admin_id=str(current_user.id))
    return user


@router.patch("/users/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Deactivate a user account — admin only"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    user.is_active = False
    await db.flush()
    logger.info("user_deactivated", user_id=str(user_id), admin_id=str(current_user.id))
    return user


# ── Doctor Verification ────────────────────────────────────────────────────

@router.patch("/doctors/{doctor_id}/verify", response_model=DoctorResponse)
async def verify_doctor(
    doctor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Verify a doctor's credentials — admin only"""
    result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
    doctor = result.scalar_one_or_none()

    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    doctor.is_verified = True
    await db.flush()
    logger.info("doctor_verified", doctor_id=str(doctor_id), admin_id=str(current_user.id))
    return doctor


# ── Audit Logs ─────────────────────────────────────────────────────────────

@router.get("/audit-logs")
async def get_audit_logs(
    user_id: Optional[UUID] = Query(None),
    action: Optional[str] = Query(None),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get audit logs with filters — admin only"""
    filters = []

    if user_id:
        filters.append(AuditLog.user_id == user_id)
    if action:
        filters.append(AuditLog.action.ilike(f"%{action}%"))
    if from_date:
        filters.append(AuditLog.created_at >= from_date)
    if to_date:
        filters.append(AuditLog.created_at <= to_date)

    result = await db.execute(
        select(AuditLog)
        .where(and_(*filters) if filters else True)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .order_by(AuditLog.created_at.desc())
    )
    logs = result.scalars().all()

    return {
        "items": [
            {
                "id": str(log.id),
                "user_id": str(log.user_id) if log.user_id else None,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "ip_address": log.ip_address,
                "status": log.status,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ],
        "page": page,
        "page_size": page_size
    }