import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, 
    Text, Enum, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship as orm_relationship
from backend.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class UserRole(str, enum.Enum):
    ELDERLY = "elderly"
    FAMILY = "family"
    CARETAKER = "caretaker"

class DoseStatus(str, enum.Enum):
    TAKEN = "taken"
    SKIPPED = "skipped"
    MISSED = "missed"

class AppointmentStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class NotificationStatus(str, enum.Enum):
    SENT = "sent"
    MOCKED_NO_KEY = "mocked_no_key"
    FAILED = "failed"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.ELDERLY, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    owned_profiles = orm_relationship("ElderlyProfile", back_populates="owner", cascade="all, delete-orphan")
    circle_memberships = orm_relationship("CareCircleMember", back_populates="user", cascade="all, delete-orphan")

class ElderlyProfile(Base):
    __tablename__ = "elderly_profiles"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(String(255), nullable=False)
    date_of_birth = Column(String(50), nullable=True)
    primary_phone = Column(String(50), nullable=True)
    address = Column(String(255), nullable=True)
    emergency_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    owner = orm_relationship("User", back_populates="owned_profiles")
    circle_members = orm_relationship("CareCircleMember", back_populates="profile", cascade="all, delete-orphan")
    invites = orm_relationship("CareCircleInvite", back_populates="profile", cascade="all, delete-orphan")
    medications = orm_relationship("Medication", back_populates="profile", cascade="all, delete-orphan")
    appointments = orm_relationship("Appointment", back_populates="profile", cascade="all, delete-orphan")
    health_profile = orm_relationship("HealthProfile", back_populates="profile", uselist=False, cascade="all, delete-orphan")
    audit_logs = orm_relationship("AuditLog", back_populates="profile", cascade="all, delete-orphan")

class CareCircleMember(Base):
    __tablename__ = "care_circle_members"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("elderly_profiles.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    relationship = Column(String(100), nullable=False)  # e.g., Daughter, Son, Professional Nurse
    role = Column(Enum(UserRole), nullable=False)
    permissions = Column(String(50), default="full_access", nullable=False)  # full_access, can_log_dose, read_only
    is_active = Column(Boolean, default=True, nullable=False)
    joined_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    profile = orm_relationship("ElderlyProfile", back_populates="circle_members")
    user = orm_relationship("User", back_populates="circle_memberships")

    __table_args__ = (
        UniqueConstraint("profile_id", "user_id", name="uq_profile_user_member"),
    )

class CareCircleInvite(Base):
    __tablename__ = "care_circle_invites"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("elderly_profiles.id", ondelete="CASCADE"), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    invite_code = Column(String(32), unique=True, index=True, nullable=False)
    intended_role = Column(Enum(UserRole), nullable=False)
    intended_relationship = Column(String(100), default="Care Circle Member", nullable=False)
    permissions = Column(String(50), default="full_access", nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    used_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    profile = orm_relationship("ElderlyProfile", back_populates="invites")

class Medication(Base):
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("elderly_profiles.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    dosage = Column(String(100), nullable=False)  # e.g. "10mg"
    form = Column(String(50), default="Tablet", nullable=False)  # Tablet, Capsule, Liquid, Injection
    instructions = Column(Text, nullable=True)  # e.g., "Take after breakfast with full glass of water"
    schedule_times = Column(JSON, default=list, nullable=False)  # e.g. ["08:00", "20:00"]
    frequency = Column(String(50), default="Daily", nullable=False)
    start_date = Column(String(20), nullable=True)
    end_date = Column(String(20), nullable=True)
    prescribing_doctor = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    profile = orm_relationship("ElderlyProfile", back_populates="medications")
    dose_logs = orm_relationship("DoseLog", back_populates="medication", cascade="all, delete-orphan")

class DoseLog(Base):
    __tablename__ = "dose_logs"

    id = Column(Integer, primary_key=True, index=True)
    medication_id = Column(Integer, ForeignKey("medications.id", ondelete="CASCADE"), nullable=False)
    profile_id = Column(Integer, ForeignKey("elderly_profiles.id", ondelete="CASCADE"), nullable=False)
    recorded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    scheduled_date = Column(String(20), nullable=False)  # YYYY-MM-DD
    scheduled_time = Column(String(10), nullable=False)  # HH:MM
    recorded_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    status = Column(Enum(DoseStatus), default=DoseStatus.TAKEN, nullable=False)
    notes = Column(Text, nullable=True)

    medication = orm_relationship("Medication", back_populates="dose_logs")
    recorded_by = orm_relationship("User")

    __table_args__ = (
        UniqueConstraint("medication_id", "scheduled_date", "scheduled_time", name="uq_med_date_time_dose"),
    )

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("elderly_profiles.id", ondelete="CASCADE"), nullable=False)
    doctor_name = Column(String(255), nullable=False)
    specialty = Column(String(100), nullable=False)
    appointment_date = Column(String(20), nullable=False)  # YYYY-MM-DD
    appointment_time = Column(String(10), nullable=False)  # HH:MM
    location = Column(String(255), nullable=False)
    contact_number = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.SCHEDULED, nullable=False)
    reminder_sent = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    profile = orm_relationship("ElderlyProfile", back_populates="appointments")

class HealthProfile(Base):
    __tablename__ = "health_profiles"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("elderly_profiles.id", ondelete="CASCADE"), unique=True, nullable=False)
    blood_type = Column(String(10), nullable=True)
    allergies = Column(JSON, default=list, nullable=False)  # list of strings
    emergency_contacts = Column(JSON, default=list, nullable=False)  # list of {name, relationship, phone, priority}
    medical_conditions = Column(JSON, default=list, nullable=False)  # list of strings
    emergency_notes = Column(Text, nullable=True)
    disclaimer = Column(
        String(255), 
        default="ElderCare Connect is a collaborative coordination aid and does not provide diagnostic or prescribing medical services.",
        nullable=False
    )
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    profile = orm_relationship("ElderlyProfile", back_populates="health_profile")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("elderly_profiles.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_name = Column(String(255), nullable=True)
    action = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    profile = orm_relationship("ElderlyProfile", back_populates="audit_logs")

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("elderly_profiles.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    notification_type = Column(String(50), nullable=False)  # medication_reminder, missed_dose_alert, appointment_reminder
    recipient_email = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(Enum(NotificationStatus), nullable=False)
    external_id = Column(String(100), nullable=True)
    reference_key = Column(String(255), index=True, nullable=True)  # Used for duplicate prevention: e.g. "med:1:2026-11-15:08:00"
    sent_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
