from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from backend.models import UserRole, DoseStatus, AppointmentStatus, NotificationStatus

# --- User & Auth Schemas ---
class UserCreate(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=2)
    phone: Optional[str] = None
    role: UserRole = UserRole.ELDERLY

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    phone: Optional[str] = None
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# --- Elderly Profile Schemas ---
class ElderlyProfileCreate(BaseModel):
    full_name: str = Field(..., min_length=2)
    date_of_birth: Optional[str] = None
    primary_phone: Optional[str] = None
    address: Optional[str] = None
    emergency_notes: Optional[str] = None

class ElderlyProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    primary_phone: Optional[str] = None
    address: Optional[str] = None
    emergency_notes: Optional[str] = None

class ElderlyProfileResponse(BaseModel):
    id: int
    owner_id: int
    full_name: str
    date_of_birth: Optional[str] = None
    primary_phone: Optional[str] = None
    address: Optional[str] = None
    emergency_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Care Circle Schemas ---
class CareCircleMemberResponse(BaseModel):
    id: int
    profile_id: int
    user_id: int
    user_name: str
    user_email: str
    relationship: str
    role: UserRole
    permissions: str
    is_active: bool
    joined_at: datetime

class CareCircleInviteCreate(BaseModel):
    intended_role: UserRole = UserRole.FAMILY
    intended_relationship: str = "Family Member"
    permissions: str = "full_access"

class CareCircleInviteResponse(BaseModel):
    id: int
    profile_id: int
    invite_code: str
    intended_role: UserRole
    intended_relationship: str
    permissions: str
    expires_at: datetime
    is_used: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CareCircleAcceptInvite(BaseModel):
    invite_code: str

# --- Medication Schemas ---
class MedicationCreate(BaseModel):
    name: str = Field(..., min_length=1)
    dosage: str = Field(..., min_length=1)  # e.g., "10mg"
    form: str = "Tablet"  # Tablet, Capsule, Liquid, Injection, Inhaler, Topical
    instructions: Optional[str] = None
    schedule_times: List[str] = Field(default_factory=list)  # ["08:00", "20:00"]
    frequency: str = "Daily"
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None
    prescribing_doctor: Optional[str] = None

class MedicationUpdate(BaseModel):
    name: Optional[str] = None
    dosage: Optional[str] = None
    form: Optional[str] = None
    instructions: Optional[str] = None
    schedule_times: Optional[List[str]] = None
    frequency: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    prescribing_doctor: Optional[str] = None
    is_active: Optional[bool] = None

class NextDoseInfo(BaseModel):
    date: str
    time: str
    is_today: bool

class MedicationResponse(BaseModel):
    id: int
    profile_id: int
    name: str
    dosage: str
    form: str
    instructions: Optional[str] = None
    schedule_times: List[str]
    frequency: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    prescribing_doctor: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    next_dose: Optional[NextDoseInfo] = None

    model_config = ConfigDict(from_attributes=True)

# --- Dose Tracking Schemas ---
class DoseLogCreate(BaseModel):
    scheduled_date: str  # YYYY-MM-DD
    scheduled_time: str  # HH:MM
    status: DoseStatus = DoseStatus.TAKEN
    notes: Optional[str] = None

class DoseLogResponse(BaseModel):
    id: int
    medication_id: int
    medication_name: Optional[str] = None
    profile_id: int
    recorded_by_id: int
    recorded_by_name: Optional[str] = None
    scheduled_date: str
    scheduled_time: str
    recorded_at: datetime
    status: DoseStatus
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# --- Appointment Schemas ---
class AppointmentCreate(BaseModel):
    doctor_name: str = Field(..., min_length=2)
    specialty: str = Field(..., min_length=2)
    appointment_date: str  # YYYY-MM-DD
    appointment_time: str  # HH:MM
    location: str
    contact_number: Optional[str] = None
    notes: Optional[str] = None

class AppointmentUpdate(BaseModel):
    doctor_name: Optional[str] = None
    specialty: Optional[str] = None
    appointment_date: Optional[str] = None
    appointment_time: Optional[str] = None
    location: Optional[str] = None
    contact_number: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[AppointmentStatus] = None

class AppointmentResponse(BaseModel):
    id: int
    profile_id: int
    doctor_name: str
    specialty: str
    appointment_date: str
    appointment_time: str
    location: str
    contact_number: Optional[str] = None
    notes: Optional[str] = None
    status: AppointmentStatus
    reminder_sent: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Health Profile & Emergency Schemas ---
class EmergencyContactItem(BaseModel):
    name: str
    relationship: str
    phone: str
    priority: int = 1

class HealthProfileUpdate(BaseModel):
    blood_type: Optional[str] = None
    allergies: Optional[List[str]] = None
    emergency_contacts: Optional[List[EmergencyContactItem]] = None
    medical_conditions: Optional[List[str]] = None
    emergency_notes: Optional[str] = None

class HealthProfileResponse(BaseModel):
    id: int
    profile_id: int
    blood_type: Optional[str] = None
    allergies: List[str] = []
    emergency_contacts: List[Dict[str, Any]] = []
    medical_conditions: List[str] = []
    emergency_notes: Optional[str] = None
    disclaimer: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Audit & Notification Schemas ---
class AuditLogResponse(BaseModel):
    id: int
    profile_id: int
    user_id: int
    user_name: Optional[str] = None
    action: str
    details: Optional[str] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

class NotificationLogResponse(BaseModel):
    id: int
    profile_id: int
    user_id: Optional[int] = None
    notification_type: str
    recipient_email: str
    subject: str
    message: str
    status: NotificationStatus
    external_id: Optional[str] = None
    reference_key: Optional[str] = None
    sent_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Dashboard Summary ---
class TodayDoseItem(BaseModel):
    medication_id: int
    medication_name: str
    dosage: str
    form: str
    instructions: Optional[str] = None
    scheduled_time: str
    status: str  # "taken", "skipped", "missed", "pending"
    dose_log_id: Optional[int] = None

class DashboardSummaryResponse(BaseModel):
    profile_id: int
    elderly_name: str
    today_date: str
    taken_count: int
    missed_count: int
    pending_count: int
    total_today_doses: int
    upcoming_appointments: List[AppointmentResponse]
    today_doses: List[TodayDoseItem]
    care_circle_count: int
    recent_activity: List[AuditLogResponse]
