from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    User, ElderlyProfile, Medication, DoseLog, DoseStatus, 
    Appointment, AppointmentStatus, CareCircleMember, AuditLog
)
from backend.schemas import (
    DashboardSummaryResponse, TodayDoseItem, AppointmentResponse, 
    AuditLogResponse
)
from backend.security import get_current_user, verify_care_profile_access

router = APIRouter(prefix="/profiles/{profile_id}/dashboard", tags=["Dashboard Summary"])

@router.get("", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile = verify_care_profile_access(profile_id, current_user, db)

    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    # 1. Fetch active medications for profile
    medications = db.query(Medication).filter(
        Medication.profile_id == profile_id,
        Medication.is_active == True
    ).all()

    # 2. Fetch today's dose logs
    today_logs = db.query(DoseLog).filter(
        DoseLog.profile_id == profile_id,
        DoseLog.scheduled_date == today_str
    ).all()

    log_map = {
        (l.medication_id, l.scheduled_time): l for l in today_logs
    }

    today_doses: List[TodayDoseItem] = []
    taken_count = 0
    missed_count = 0
    pending_count = 0

    for med in medications:
        times = med.schedule_times or ["08:00"]
        for t in times:
            recorded = log_map.get((med.id, t))
            if recorded:
                stat = recorded.status.value
                dose_log_id = recorded.id
                if recorded.status == DoseStatus.TAKEN:
                    taken_count += 1
                elif recorded.status == DoseStatus.MISSED:
                    missed_count += 1
                elif recorded.status == DoseStatus.SKIPPED:
                    # treat skipped as recorded
                    pass
            else:
                stat = "pending"
                dose_log_id = None
                pending_count += 1

            today_doses.append(TodayDoseItem(
                medication_id=med.id,
                medication_name=med.name,
                dosage=med.dosage,
                form=med.form,
                instructions=med.instructions,
                scheduled_time=t,
                status=stat,
                dose_log_id=dose_log_id
            ))

    # Sort today's doses chronologically
    today_doses.sort(key=lambda x: x.scheduled_time)

    # 3. Upcoming appointments (scheduled status, date >= today)
    upcoming_apts = db.query(Appointment).filter(
        Appointment.profile_id == profile_id,
        Appointment.status == AppointmentStatus.SCHEDULED,
        Appointment.appointment_date >= today_str
    ).order_by(Appointment.appointment_date.asc(), Appointment.appointment_time.asc()).limit(5).all()

    # 4. Care circle members count
    care_circle_count = db.query(CareCircleMember).filter(
        CareCircleMember.profile_id == profile_id,
        CareCircleMember.is_active == True
    ).count()

    # 5. Recent audit activity
    recent_activity = db.query(AuditLog).filter(
        AuditLog.profile_id == profile_id
    ).order_by(AuditLog.timestamp.desc()).limit(8).all()

    return DashboardSummaryResponse(
        profile_id=profile.id,
        elderly_name=profile.full_name,
        today_date=today_str,
        taken_count=taken_count,
        missed_count=missed_count,
        pending_count=pending_count,
        total_today_doses=len(today_doses),
        upcoming_appointments=[AppointmentResponse.model_validate(a) for a in upcoming_apts],
        today_doses=today_doses,
        care_circle_count=care_circle_count,
        recent_activity=[AuditLogResponse.model_validate(a) for a in recent_activity]
    )
