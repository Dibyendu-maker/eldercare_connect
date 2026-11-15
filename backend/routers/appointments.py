from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, Appointment, AppointmentStatus
from backend.schemas import AppointmentCreate, AppointmentUpdate, AppointmentResponse
from backend.security import get_current_user, verify_care_profile_access
from backend.audit import log_audit_event
from backend.email_service import EmailService, format_appointment_reminder_email

router = APIRouter(prefix="/profiles/{profile_id}/appointments", tags=["Healthcare Appointments"])

@router.get("", response_model=List[AppointmentResponse])
def list_appointments(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_care_profile_access(profile_id, current_user, db)
    appointments = db.query(Appointment).filter(
        Appointment.profile_id == profile_id
    ).order_by(Appointment.appointment_date.asc(), Appointment.appointment_time.asc()).all()
    return appointments

@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
def create_appointment(
    profile_id: int,
    apt_in: AppointmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile = verify_care_profile_access(profile_id, current_user, db, require_write=True)

    apt = Appointment(
        profile_id=profile_id,
        doctor_name=apt_in.doctor_name,
        specialty=apt_in.specialty,
        appointment_date=apt_in.appointment_date,
        appointment_time=apt_in.appointment_time,
        location=apt_in.location,
        contact_number=apt_in.contact_number,
        notes=apt_in.notes,
        status=AppointmentStatus.SCHEDULED,
        reminder_sent=False
    )
    db.add(apt)
    db.commit()
    db.refresh(apt)

    log_audit_event(
        db, profile_id, current_user, "APPOINTMENT_SCHEDULED",
        f"Scheduled appointment with Dr. {apt.doctor_name} ({apt.specialty}) on {apt.appointment_date} at {apt.appointment_time}"
    )

    return apt

@router.put("/{appointment_id}", response_model=AppointmentResponse)
def update_appointment(
    profile_id: int,
    appointment_id: int,
    apt_in: AppointmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_care_profile_access(profile_id, current_user, db, require_write=True)
    apt = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.profile_id == profile_id
    ).first()

    if not apt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    if apt_in.doctor_name is not None:
        apt.doctor_name = apt_in.doctor_name
    if apt_in.specialty is not None:
        apt.specialty = apt_in.specialty
    if apt_in.appointment_date is not None:
        apt.appointment_date = apt_in.appointment_date
    if apt_in.appointment_time is not None:
        apt.appointment_time = apt_in.appointment_time
    if apt_in.location is not None:
        apt.location = apt_in.location
    if apt_in.contact_number is not None:
        apt.contact_number = apt_in.contact_number
    if apt_in.notes is not None:
        apt.notes = apt_in.notes
    if apt_in.status is not None:
        apt.status = apt_in.status

    db.commit()
    db.refresh(apt)

    log_audit_event(
        db, profile_id, current_user, "APPOINTMENT_UPDATED",
        f"Updated appointment with Dr. {apt.doctor_name} (Status: {apt.status.value})"
    )

    return apt

@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
def cancel_appointment(
    profile_id: int,
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_care_profile_access(profile_id, current_user, db, require_write=True)
    apt = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.profile_id == profile_id
    ).first()

    if not apt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    apt.status = AppointmentStatus.CANCELLED
    db.commit()
    db.refresh(apt)

    log_audit_event(
        db, profile_id, current_user, "APPOINTMENT_CANCELLED",
        f"Cancelled appointment with Dr. {apt.doctor_name} on {apt.appointment_date}"
    )

    return apt

@router.post("/{appointment_id}/send-reminder")
def send_appointment_reminder(
    profile_id: int,
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile = verify_care_profile_access(profile_id, current_user, db)
    apt = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.profile_id == profile_id
    ).first()

    if not apt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    owner = db.query(User).filter(User.id == profile.owner_id).first()
    recipient_email = owner.email if owner else current_user.email

    ref_key = f"apt_remind:{apt.id}:{apt.appointment_date}"
    email_result = EmailService.send_email(
        db=db,
        profile_id=profile_id,
        recipient_email=recipient_email,
        subject=f"Appointment Reminder: Dr. {apt.doctor_name} on {apt.appointment_date}",
        html_content=format_appointment_reminder_email(
            elderly_name=profile.full_name,
            doctor=apt.doctor_name,
            specialty=apt.specialty,
            date=apt.appointment_date,
            time=apt.appointment_time,
            location=apt.location
        ),
        notification_type="appointment_reminder",
        reference_key=ref_key,
        user_id=owner.id if owner else current_user.id
    )

    apt.reminder_sent = True
    db.commit()

    return email_result
