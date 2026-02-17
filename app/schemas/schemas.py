from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from app.models.models import UserRole, ConsultationStatus, PaymentStatus, SlotStatus


# ── Base ───────────────────────────────────────────────────────────────────

class BaseResponse(BaseModel):
    class Config:
        from_attributes = True


# ── Auth Schemas ───────────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{9,14}$")
    role: UserRole = UserRole.PATIENT
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)

    @validator("password")
    def validate_password(cls, v):
        from app.core.security import validate_password_strength
        is_valid, message = validate_password_strength(v)
        if not is_valid:
            raise ValueError(message)
        return v


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_token: Optional[str] = Field(None, min_length=6, max_length=6)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    role: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class MFASetupResponse(BaseModel):
    secret: str
    qr_code: str
    message: str


class MFAVerifyRequest(BaseModel):
    token: str = Field(..., min_length=6, max_length=6)


# ── User Schemas ───────────────────────────────────────────────────────────

class UserProfileUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pincode: Optional[str] = None
    medical_history: Optional[Dict[str, Any]] = None


class UserResponse(BaseResponse):
    id: UUID
    email: str
    phone: Optional[str]
    role: UserRole
    is_active: bool
    is_verified: bool
    mfa_enabled: bool
    created_at: datetime


class UserProfileResponse(BaseResponse):
    id: UUID
    user_id: UUID
    first_name: str
    last_name: str
    date_of_birth: Optional[datetime]
    gender: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]


# ── Doctor Schemas ─────────────────────────────────────────────────────────

class DoctorCreateRequest(BaseModel):
    license_number: str = Field(..., min_length=5, max_length=100)
    specialization: str = Field(..., min_length=2, max_length=200)
    qualification: str = Field(..., min_length=2, max_length=500)
    experience_years: int = Field(..., ge=0, le=60)
    consultation_fee: float = Field(..., gt=0)
    bio: Optional[str] = None
    languages: List[str] = ["English"]


class DoctorUpdateRequest(BaseModel):
    specialization: Optional[str] = None
    consultation_fee: Optional[float] = Field(None, gt=0)
    bio: Optional[str] = None
    languages: Optional[List[str]] = None
    is_available: Optional[bool] = None


class DoctorResponse(BaseResponse):
    id: UUID
    user_id: UUID
    license_number: str
    specialization: str
    qualification: str
    experience_years: int
    consultation_fee: float
    bio: Optional[str]
    languages: List[str]
    rating: float
    total_consultations: int
    is_verified: bool
    is_available: bool


class DoctorSearchRequest(BaseModel):
    specialization: Optional[str] = None
    min_fee: Optional[float] = None
    max_fee: Optional[float] = None
    min_experience: Optional[int] = None
    language: Optional[str] = None
    available_date: Optional[datetime] = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


# ── Availability Slot Schemas ──────────────────────────────────────────────

class SlotCreateRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    is_recurring: bool = False
    recurrence_rule: Optional[str] = None

    @validator("end_time")
    def end_time_after_start(cls, v, values):
        if "start_time" in values and v <= values["start_time"]:
            raise ValueError("end_time must be after start_time")
        return v


class SlotResponse(BaseResponse):
    id: UUID
    doctor_id: UUID
    start_time: datetime
    end_time: datetime
    status: SlotStatus
    is_recurring: bool


# ── Consultation Schemas ───────────────────────────────────────────────────

class ConsultationBookRequest(BaseModel):
    doctor_id: UUID
    slot_id: UUID
    chief_complaint: str = Field(..., min_length=10, max_length=1000)
    consultation_type: str = Field("video", pattern="^(video|audio|chat)$")
    idempotency_key: str = Field(..., min_length=10, max_length=255)


class ConsultationUpdateRequest(BaseModel):
    status: Optional[ConsultationStatus] = None
    notes: Optional[str] = None
    diagnosis: Optional[str] = None
    follow_up_date: Optional[datetime] = None


class ConsultationResponse(BaseResponse):
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    slot_id: UUID
    status: ConsultationStatus
    chief_complaint: str
    notes: Optional[str]
    diagnosis: Optional[str]
    follow_up_date: Optional[datetime]
    consultation_type: str
    meeting_url: Optional[str]
    created_at: datetime


# ── Prescription Schemas ───────────────────────────────────────────────────

class MedicationItem(BaseModel):
    name: str = Field(..., min_length=1)
    dosage: str = Field(..., min_length=1)
    frequency: str = Field(..., min_length=1)
    duration: str = Field(..., min_length=1)
    instructions: Optional[str] = None


class PrescriptionCreateRequest(BaseModel):
    consultation_id: UUID
    medications: List[MedicationItem] = Field(..., min_items=1)
    instructions: Optional[str] = None
    valid_until: Optional[datetime] = None


class PrescriptionResponse(BaseResponse):
    id: UUID
    consultation_id: UUID
    medications: List[Dict[str, Any]]
    instructions: Optional[str]
    valid_until: Optional[datetime]
    is_active: bool
    created_at: datetime


# ── Payment Schemas ────────────────────────────────────────────────────────

class PaymentCreateRequest(BaseModel):
    consultation_id: UUID
    payment_gateway: str = Field("razorpay", pattern="^(razorpay|stripe|paytm)$")
    idempotency_key: str = Field(..., min_length=10, max_length=255)


class PaymentResponse(BaseResponse):
    id: UUID
    consultation_id: UUID
    amount: float
    currency: str
    status: PaymentStatus
    payment_gateway: Optional[str]
    gateway_transaction_id: Optional[str]
    created_at: datetime


# ── Pagination ─────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── Admin Analytics ────────────────────────────────────────────────────────

class AnalyticsResponse(BaseModel):
    total_users: int
    total_doctors: int
    total_consultations: int
    consultations_today: int
    revenue_today: float
    revenue_total: float
    top_specializations: List[Dict[str, Any]]
    consultation_status_breakdown: Dict[str, int]