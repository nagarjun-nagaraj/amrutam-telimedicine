from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
from typing import Optional
from uuid import UUID
from app.db.session import get_db
from app.models.models import (
    Consultation, AvailabilitySlot, Doctor, User,
    SlotStatus, ConsultationStatus, Prescription, Payment,
    PaymentStatus, UserRole
)
from app.schemas.schemas import (
    ConsultationBookRequest, ConsultationUpdateRequest,
    ConsultationResponse, PrescriptionCreateRequest,
    PrescriptionResponse, PaymentCreateRequest, PaymentResponse,
    PaginatedResponse
)
from app.core.dependencies import (
    get_current_active_user, require_doctor, require_patient
)
from app.core.logging import get_logger
import uuid

logger = get_logger(__name__)

router = APIRouter(prefix="/consultations", tags=["Consultations"])


# ── Book Consultation ──────────────────────────────────────────────────────

@router.post("", response_model=ConsultationResponse, status_code=status.HTTP_201_CREATED)
async def book_consultation(
    body: ConsultationBookRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Book a consultation slot.
    Idempotent — same idempotency_key returns existing booking.
    """
    # Idempotency check
    result = await db.execute(
        select(Consultation).where(
            Consultation.idempotency_key == body.idempotency_key
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        logger.info("idempotent_booking_returned", key=body.idempotency_key)
        return existing

    # Verify doctor exists
    result = await db.execute(
        select(Doctor).where(Doctor.id == body.doctor_id)
    )
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Lock slot row for update (prevents double booking)
    result = await db.execute(
        select(AvailabilitySlot)
        .where(
            and_(
                AvailabilitySlot.id == body.slot_id,
                AvailabilitySlot.doctor_id == body.doctor_id
            )
        )
        .with_for_update()
    )
    slot = result.scalar_one_or_none()

    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    if slot.status != SlotStatus.AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Slot is no longer available"
        )

    # Mark slot as booked
    slot.status = SlotStatus.BOOKED

    # Create consultation
    consultation = Consultation(
        patient_id=current_user.id,
        doctor_id=body.doctor_id,
        slot_id=body.slot_id,
        chief_complaint=body.chief_complaint,
        consultation_type=body.consultation_type,
        idempotency_key=body.idempotency_key,
        status=ConsultationStatus.SCHEDULED,
        meeting_url=f"https://meet.amrutam.com/{uuid.uuid4()}"
    )
    db.add(consultation)
    await db.flush()

    # Create pending payment
    payment = Payment(
        consultation_id=consultation.id,
        amount=doctor.consultation_fee,
        currency="INR",
        status=PaymentStatus.PENDING,
        idempotency_key=f"pay_{body.idempotency_key}"
    )
    db.add(payment)
    await db.flush()

    logger.info(
        "consultation_booked",
        consultation_id=str(consultation.id),
        patient_id=str(current_user.id),
        doctor_id=str(body.doctor_id)
    )

    return consultation


# ── Get Consultations ──────────────────────────────────────────────────────

@router.get("", response_model=PaginatedResponse)
async def get_consultations(
    status_filter: Optional[ConsultationStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get consultations for current user (patient sees own, doctor sees own)"""
    from sqlalchemy import func

    if current_user.role == UserRole.PATIENT:
        filters = [Consultation.patient_id == current_user.id]
    elif current_user.role == UserRole.DOCTOR:
        result = await db.execute(
            select(Doctor).where(Doctor.user_id == current_user.id)
        )
        doctor = result.scalar_one_or_none()
        if not doctor:
            raise HTTPException(status_code=404, detail="Doctor profile not found")
        filters = [Consultation.doctor_id == doctor.id]
    else:
        filters = []

    if status_filter:
        filters.append(Consultation.status == status_filter)

    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count(Consultation.id)).where(and_(*filters))
    )
    total = count_result.scalar()

    result = await db.execute(
        select(Consultation)
        .where(and_(*filters))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .order_by(Consultation.created_at.desc())
    )
    consultations = result.scalars().all()

    return PaginatedResponse(
        items=[ConsultationResponse.model_validate(c) for c in consultations],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )


@router.get("/{consultation_id}", response_model=ConsultationResponse)
async def get_consultation(
    consultation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a single consultation by ID"""
    result = await db.execute(
        select(Consultation).where(Consultation.id == consultation_id)
    )
    consultation = result.scalar_one_or_none()

    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")

    # Access control
    if current_user.role == UserRole.PATIENT:
        if consultation.patient_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")

    return consultation


# ── Update Consultation ────────────────────────────────────────────────────

@router.patch("/{consultation_id}", response_model=ConsultationResponse)
async def update_consultation(
    consultation_id: UUID,
    body: ConsultationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor)
):
    """Update consultation status, notes, diagnosis (doctor only)"""
    result = await db.execute(
        select(Consultation).where(Consultation.id == consultation_id)
    )
    consultation = result.scalar_one_or_none()

    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")

    # Verify doctor owns this consultation
    doc_result = await db.execute(
        select(Doctor).where(Doctor.user_id == current_user.id)
    )
    doctor = doc_result.scalar_one_or_none()

    if not doctor or (consultation.doctor_id != doctor.id and current_user.role != UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Not authorized")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(consultation, field, value)

    # If completed, update doctor stats
    if body.status == ConsultationStatus.COMPLETED:
        await db.execute(
            update(Doctor)
            .where(Doctor.id == consultation.doctor_id)
            .values(total_consultations=Doctor.total_consultations + 1)
        )

    await db.flush()
    logger.info("consultation_updated", consultation_id=str(consultation_id))
    return consultation


# ── Prescriptions ──────────────────────────────────────────────────────────

@router.post("/{consultation_id}/prescriptions", response_model=PrescriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_prescription(
    consultation_id: UUID,
    body: PrescriptionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor)
):
    """Create prescription for a completed consultation (doctor only)"""
    result = await db.execute(
        select(Consultation).where(Consultation.id == consultation_id)
    )
    consultation = result.scalar_one_or_none()

    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")

    if consultation.status != ConsultationStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail="Prescription can only be created for completed consultations"
        )

    # Check existing prescription
    result = await db.execute(
        select(Prescription).where(Prescription.consultation_id == consultation_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Prescription already exists for this consultation"
        )

    prescription = Prescription(
        consultation_id=consultation_id,
        medications=[m.model_dump() for m in body.medications],
        instructions=body.instructions,
        valid_until=body.valid_until,
    )
    db.add(prescription)
    await db.flush()

    logger.info("prescription_created", consultation_id=str(consultation_id))
    return prescription


@router.get("/{consultation_id}/prescriptions", response_model=PrescriptionResponse)
async def get_prescription(
    consultation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get prescription for a consultation"""
    result = await db.execute(
        select(Prescription).where(Prescription.consultation_id == consultation_id)
    )
    prescription = result.scalar_one_or_none()

    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    return prescription


# ── Payments ───────────────────────────────────────────────────────────────

@router.post("/{consultation_id}/payments", response_model=PaymentResponse)
async def process_payment(
    consultation_id: UUID,
    body: PaymentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Process payment for a consultation (idempotent)"""
    # Idempotency check
    result = await db.execute(
        select(Payment).where(Payment.idempotency_key == body.idempotency_key)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    result = await db.execute(
        select(Payment).where(Payment.consultation_id == consultation_id)
    )
    payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment record not found")

    if payment.status == PaymentStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Payment already completed")

    # Simulate payment processing
    payment.status = PaymentStatus.COMPLETED
    payment.payment_gateway = body.payment_gateway
    payment.gateway_transaction_id = f"txn_{uuid.uuid4().hex[:16]}"
    payment.idempotency_key = body.idempotency_key

    await db.flush()
    logger.info("payment_processed", consultation_id=str(consultation_id))
    return payment


@router.get("/{consultation_id}/payments", response_model=PaymentResponse)
async def get_payment(
    consultation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get payment details for a consultation"""
    result = await db.execute(
        select(Payment).where(Payment.consultation_id == consultation_id)
    )
    payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    return payment