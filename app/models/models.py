import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey,
    Text, Integer, Numeric, Enum, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db.session import Base


# ── Enums ──────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    ADMIN = "admin"


class ConsultationStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class SlotStatus(str, enum.Enum):
    AVAILABLE = "available"
    BOOKED = "booked"
    BLOCKED = "blocked"


# ── Base Mixin ─────────────────────────────────────────────────────────────

class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# ── Users ──────────────────────────────────────────────────────────────────

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), unique=True, nullable=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.PATIENT)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    mfa_secret = Column(String(32), nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    doctor_profile = relationship("Doctor", back_populates="user", uselist=False, cascade="all, delete-orphan")
    consultations_as_patient = relationship("Consultation", foreign_keys="Consultation.patient_id", back_populates="patient")
    audit_logs = relationship("AuditLog", back_populates="user")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_users_email_active", "email", "is_active"),
    )


class UserProfile(Base, TimestampMixin):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    date_of_birth = Column(DateTime, nullable=True)
    gender = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    country = Column(String(100), default="India")
    pincode = Column(String(10), nullable=True)
    profile_picture_url = Column(String(500), nullable=True)
    medical_history = Column(JSONB, default=dict)

    # Relationships
    user = relationship("User", back_populates="profile")


# ── Doctors ────────────────────────────────────────────────────────────────

class Doctor(Base, TimestampMixin):
    __tablename__ = "doctors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    license_number = Column(String(100), unique=True, nullable=False)
    specialization = Column(String(200), nullable=False, index=True)
    qualification = Column(String(500), nullable=False)
    experience_years = Column(Integer, default=0, nullable=False)
    consultation_fee = Column(Numeric(10, 2), nullable=False)
    bio = Column(Text, nullable=True)
    languages = Column(JSONB, default=list)
    rating = Column(Numeric(3, 2), default=0.0)
    total_consultations = Column(Integer, default=0)
    is_verified = Column(Boolean, default=False)
    is_available = Column(Boolean, default=True)

    # Relationships
    user = relationship("User", back_populates="doctor_profile")
    availability_slots = relationship("AvailabilitySlot", back_populates="doctor", cascade="all, delete-orphan")
    consultations = relationship("Consultation", foreign_keys="Consultation.doctor_id", back_populates="doctor")

    __table_args__ = (
        Index("ix_doctors_specialization_available", "specialization", "is_available"),
    )


# ── Availability Slots ─────────────────────────────────────────────────────

class AvailabilitySlot(Base, TimestampMixin):
    __tablename__ = "availability_slots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    status = Column(Enum(SlotStatus), default=SlotStatus.AVAILABLE, nullable=False)
    is_recurring = Column(Boolean, default=False)
    recurrence_rule = Column(String(200), nullable=True)

    # Relationships
    doctor = relationship("Doctor", back_populates="availability_slots")
    consultation = relationship("Consultation", back_populates="slot", uselist=False)

    __table_args__ = (
        Index("ix_slots_doctor_time", "doctor_id", "start_time", "status"),
        UniqueConstraint("doctor_id", "start_time", name="uq_doctor_slot_time"),
    )


# ── Consultations ──────────────────────────────────────────────────────────

class Consultation(Base, TimestampMixin):
    __tablename__ = "consultations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False)
    slot_id = Column(UUID(as_uuid=True), ForeignKey("availability_slots.id", ondelete="RESTRICT"), unique=True, nullable=False)
    status = Column(Enum(ConsultationStatus), default=ConsultationStatus.SCHEDULED, nullable=False)
    chief_complaint = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    diagnosis = Column(Text, nullable=True)
    follow_up_date = Column(DateTime(timezone=True), nullable=True)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    consultation_type = Column(String(50), default="video")
    meeting_url = Column(String(500), nullable=True)

    # Relationships
    patient = relationship("User", foreign_keys=[patient_id], back_populates="consultations_as_patient")
    doctor = relationship("Doctor", foreign_keys=[doctor_id], back_populates="consultations")
    slot = relationship("AvailabilitySlot", back_populates="consultation")
    prescription = relationship("Prescription", back_populates="consultation", uselist=False, cascade="all, delete-orphan")
    payment = relationship("Payment", back_populates="consultation", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_consultations_patient_status", "patient_id", "status"),
        Index("ix_consultations_doctor_status", "doctor_id", "status"),
    )


# ── Prescriptions ──────────────────────────────────────────────────────────

class Prescription(Base, TimestampMixin):
    __tablename__ = "prescriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consultation_id = Column(UUID(as_uuid=True), ForeignKey("consultations.id", ondelete="CASCADE"), unique=True, nullable=False)
    medications = Column(JSONB, nullable=False, default=list)
    instructions = Column(Text, nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    digital_signature = Column(String(500), nullable=True)

    # Relationships
    consultation = relationship("Consultation", back_populates="prescription")


# ── Payments ───────────────────────────────────────────────────────────────

class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consultation_id = Column(UUID(as_uuid=True), ForeignKey("consultations.id", ondelete="RESTRICT"), unique=True, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="INR")
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    payment_gateway = Column(String(50), nullable=True)
    gateway_transaction_id = Column(String(255), nullable=True, unique=True)
    idempotency_key = Column(String(255), unique=True, nullable=False)
    payment_metadata = Column(JSONB, default=dict)

    # Relationships
    consultation = relationship("Consultation", back_populates="payment")


# ── Audit Logs ─────────────────────────────────────────────────────────────

class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    old_values = Column(JSONB, nullable=True)
    new_values = Column(JSONB, nullable=True)
    status = Column(String(20), default="success")
    error_message = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_user_action", "user_id", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
    )


# ── Refresh Tokens ─────────────────────────────────────────────────────────

class RefreshToken(Base, TimestampMixin):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_revoked = Column(Boolean, default=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (
        Index("ix_refresh_tokens_user_revoked", "user_id", "is_revoked"),
    )