from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import Optional
from uuid import UUID
from app.db.session import get_db
from app.models.models import Doctor, User, UserRole, AvailabilitySlot, SlotStatus
from app.schemas.schemas import (
    DoctorCreateRequest, DoctorUpdateRequest,
    DoctorResponse, SlotCreateRequest, SlotResponse, PaginatedResponse
)
from app.core.dependencies import get_current_active_user, require_doctor, require_admin
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/doctors", tags=["Doctors"])


# ── Doctor Profile ─────────────────────────────────────────────────────────

@router.post("", response_model=DoctorResponse, status_code=status.HTTP_201_CREATED)
async def create_doctor_profile(
    body: DoctorCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create doctor profile for a registered user"""
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only users with doctor role can create doctor profiles"
        )

    # Check if profile already exists
    result = await db.execute(
        select(Doctor).where(Doctor.user_id == current_user.id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Doctor profile already exists"
        )

    # Check license number uniqueness
    result = await db.execute(
        select(Doctor).where(Doctor.license_number == body.license_number)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="License number already registered"
        )

    doctor = Doctor(
        user_id=current_user.id,
        license_number=body.license_number,
        specialization=body.specialization,
        qualification=body.qualification,
        experience_years=body.experience_years,
        consultation_fee=body.consultation_fee,
        bio=body.bio,
        languages=body.languages,
    )
    db.add(doctor)
    await db.flush()

    logger.info("doctor_profile_created", doctor_id=str(doctor.id))
    return doctor


@router.get("", response_model=PaginatedResponse)
async def search_doctors(
    specialization: Optional[str] = Query(None),
    min_fee: Optional[float] = Query(None, ge=0),
    max_fee: Optional[float] = Query(None, ge=0),
    min_experience: Optional[int] = Query(None, ge=0),
    language: Optional[str] = Query(None),
    is_available: Optional[bool] = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Search and filter doctors"""
    filters = [Doctor.is_verified == True]

    if specialization:
        filters.append(Doctor.specialization.ilike(f"%{specialization}%"))
    if min_fee is not None:
        filters.append(Doctor.consultation_fee >= min_fee)
    if max_fee is not None:
        filters.append(Doctor.consultation_fee <= max_fee)
    if min_experience is not None:
        filters.append(Doctor.experience_years >= min_experience)
    if is_available is not None:
        filters.append(Doctor.is_available == is_available)
    if language:
        filters.append(Doctor.languages.contains([language]))

    # Count total
    count_result = await db.execute(
        select(func.count(Doctor.id)).where(and_(*filters))
    )
    total = count_result.scalar()

    # Fetch page
    result = await db.execute(
        select(Doctor)
        .where(and_(*filters))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .order_by(Doctor.rating.desc())
    )
    doctors = result.scalars().all()

    return PaginatedResponse(
        items=[DoctorResponse.model_validate(d) for d in doctors],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )


@router.get("/{doctor_id}", response_model=DoctorResponse)
async def get_doctor(
    doctor_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get doctor by ID"""
    result = await db.execute(
        select(Doctor).where(Doctor.id == doctor_id)
    )
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    return doctor


@router.patch("/{doctor_id}", response_model=DoctorResponse)
async def update_doctor(
    doctor_id: UUID,
    body: DoctorUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor)
):
    """Update doctor profile"""
    result = await db.execute(
        select(Doctor).where(Doctor.id == doctor_id)
    )
    doctor = result.scalar_one_or_none()

    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    if doctor.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(doctor, field, value)

    await db.flush()
    return doctor


# ── Availability Slots ─────────────────────────────────────────────────────

@router.post("/{doctor_id}/slots", response_model=SlotResponse, status_code=status.HTTP_201_CREATED)
async def create_slot(
    doctor_id: UUID,
    body: SlotCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor)
):
    """Create availability slot for a doctor"""
    result = await db.execute(
        select(Doctor).where(Doctor.id == doctor_id)
    )
    doctor = result.scalar_one_or_none()

    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    if doctor.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Check for overlapping slots
    result = await db.execute(
        select(AvailabilitySlot).where(
            and_(
                AvailabilitySlot.doctor_id == doctor_id,
                AvailabilitySlot.status != SlotStatus.BLOCKED,
                or_(
                    and_(
                        AvailabilitySlot.start_time <= body.start_time,
                        AvailabilitySlot.end_time > body.start_time
                    ),
                    and_(
                        AvailabilitySlot.start_time < body.end_time,
                        AvailabilitySlot.end_time >= body.end_time
                    )
                )
            )
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Slot overlaps with existing slot"
        )

    slot = AvailabilitySlot(
        doctor_id=doctor_id,
        start_time=body.start_time,
        end_time=body.end_time,
        is_recurring=body.is_recurring,
        recurrence_rule=body.recurrence_rule,
    )
    db.add(slot)
    await db.flush()

    logger.info("slot_created", slot_id=str(slot.id), doctor_id=str(doctor_id))
    return slot


@router.get("/{doctor_id}/slots", response_model=list[SlotResponse])
async def get_doctor_slots(
    doctor_id: UUID,
    status_filter: Optional[SlotStatus] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db)
):
    """Get all availability slots for a doctor"""
    filters = [AvailabilitySlot.doctor_id == doctor_id]

    if status_filter:
        filters.append(AvailabilitySlot.status == status_filter)

    result = await db.execute(
        select(AvailabilitySlot)
        .where(and_(*filters))
        .order_by(AvailabilitySlot.start_time)
    )
    return result.scalars().all()