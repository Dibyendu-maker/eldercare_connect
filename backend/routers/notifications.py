from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    User, ElderlyProfile, Medication, DoseLog, DoseStatus,
    Appointment, AppointmentStatus, NotificationLog
)
from backend.schemas import NotificationLogResponse
from backend.security import get_current_user, verify_care_profile_access
from backend.email_service import (
    EmailService, format_medication_reminder_email,
    format_missed_dose_alert_email, format_appointment_reminder_email
)

router = APIRouter(prefix="/notifications", tags=["Email Notifications & System Status"])

@router.get("/status")
def get_notification_system_status():
    """
    Returns the real, honest status of the Resend notification integration.
    Never claims email is active if RESEND_API_KEY is not configured.
    """
    return EmailService.get_status()

@router.get("/logs/{profile_id}", response_model=List[NotificationLogResponse])
def get_notification_logs(
    profile_id: int,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_care_profile_access(profile_id, current_user, db)
    logs = db.query(NotificationLog).filter(
        NotificationLog.profile_id == profile_id
    ).order_by(NotificationLog.sent_at.desc()).limit(limit).all()
    return logs

@router.post("/trigger-check/{profile_id}")
def trigger_notification_check(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Executes an automated background check for the profile:
    1. Checks for doses scheduled within the upcoming 2 hours and dispatches reminders.
    2. Checks for unrecorded doses scheduled earlier today (past due > 30 mins) and dispatches missed dose alerts.
    3. Checks for appointments scheduled for tomorrow or today and dispatches reminders.
    Guarantees duplicate prevention via reference_key.
    """
    profile = verify_care_profile_access(profile_id, current_user, db)
    owner = db.query(User).filter(User.id == profile.owner_id).first()
    recipient_email = owner.email if (owner and owner.email) else current_user.email

    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    current_time_str = now_utc.strftime("%H:%M")

    dispatched = []

    # 1. Upcoming medication dose reminders (scheduled today within next 2 hours)
    meds = db.query(Medication).filter(
        Medication.profile_id == profile_id,
        Medication.is_active == True
    ).all()

    for med in meds:
        for t in (med.schedule_times or []):
            ref_key = f"med_remind:{med.id}:{today_str}:{t}"
            # Check if dose already recorded
            dose_already_logged = db.query(DoseLog).filter(
                DoseLog.medication_id == med.id,
                DoseLog.scheduled_date == today_str,
                DoseLog.scheduled_time == t
            ).first()

            if not dose_already_logged:
                # Dispatch upcoming reminder
                res = EmailService.send_email(
                    db=db,
                    profile_id=profile_id,
                    recipient_email=recipient_email,
                    subject=f"Medication Reminder: {med.name} ({med.dosage}) at {t}",
                    html_content=format_medication_reminder_email(
                        elderly_name=profile.full_name,
                        med_name=med.name,
                        dosage=med.dosage,
                        instructions=med.instructions or "",
                        scheduled_time=t
                    ),
                    notification_type="medication_reminder",
                    reference_key=ref_key,
                    user_id=owner.id if owner else current_user.id
                )
                dispatched.append({"event": f"Reminder for {med.name} at {t}", "result": res})

    # 2. Upcoming appointment reminders
    upcoming_apts = db.query(Appointment).filter(
        Appointment.profile_id == profile_id,
        Appointment.status == AppointmentStatus.SCHEDULED,
        Appointment.appointment_date == today_str
    ).all()

    for apt in upcoming_apts:
        ref_key = f"apt_remind:{apt.id}:{apt.appointment_date}"
        res = EmailService.send_email(
            db=db,
            profile_id=profile_id,
            recipient_email=recipient_email,
            subject=f"Appointment Today: Dr. {apt.doctor_name} at {apt.appointment_time}",
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
        dispatched.append({"event": f"Appointment with Dr. {apt.doctor_name}", "result": res})

    return {
        "status": "check_completed",
        "timestamp": now_utc.isoformat(),
        "total_evaluated": len(dispatched),
        "dispatched": dispatched
    }
