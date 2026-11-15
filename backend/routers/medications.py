from typing import List, Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, Medication, DoseLog, DoseStatus, ElderlyProfile
from backend.schemas import (
    MedicationCreate, MedicationUpdate, MedicationResponse,
    DoseLogCreate, DoseLogResponse, NextDoseInfo
)
from backend.security import get_current_user, verify_care_profile_access
from backend.audit import log_audit_event
from backend.email_service import (
    EmailService, format_missed_dose_alert_email
)

router = APIRouter(prefix="/profiles/{profile_id}/medications", tags=["Medications & Dose Adherence"])

def calculate_next_dose(schedule_times: List[str]) -> Optional[NextDoseInfo]:
    if not schedule_times:
        return None
    
    sorted_times = sorted(schedule_times)
    now_utc = datetime.now(timezone.utc)
    current_time_str = now_utc.strftime("%H:%M")
    today_str = now_utc.strftime("%Y-%m-%d")

    # Look for a dose later today
    for t in sorted_times:
        if t >= current_time_str:
            return NextDoseInfo(date=today_str, time=t, is_today=True)

    # Otherwise earliest dose tomorrow
    tomorrow_str = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")
    return NextDoseInfo(date=tomorrow_str, time=sorted_times[0], is_today=False)

@router.get("", response_model=List[MedicationResponse])
def list_medications(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_care_profile_access(profile_id, current_user, db)
    meds = db.query(Medication).filter(
        Medication.profile_id == profile_id,
        Medication.is_active == True
    ).order_by(Medication.name.asc()).all()

    result = []
    for med in meds:
        next_d = calculate_next_dose(med.schedule_times)
        med_dict = MedicationResponse.model_validate(med)
        med_dict.next_dose = next_d
        result.append(med_dict)

    return result

@router.post("", response_model=MedicationResponse, status_code=status.HTTP_201_CREATED)
def create_medication(
    profile_id: int,
    med_in: MedicationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile = verify_care_profile_access(profile_id, current_user, db, require_write=True)

    med = Medication(
        profile_id=profile_id,
        name=med_in.name,
        dosage=med_in.dosage,
        form=med_in.form,
        instructions=med_in.instructions,
        schedule_times=med_in.schedule_times or ["08:00"],
        frequency=med_in.frequency,
        start_date=med_in.start_date,
        end_date=med_in.end_date,
        prescribing_doctor=med_in.prescribing_doctor,
        is_active=True
    )
    db.add(med)
    db.commit()
    db.refresh(med)

    log_audit_event(
        db, profile_id, current_user, "MEDICATION_ADDED",
        f"Added medication {med.name} ({med.dosage}) scheduled at {', '.join(med.schedule_times)}"
    )

    resp = MedicationResponse.model_validate(med)
    resp.next_dose = calculate_next_dose(med.schedule_times)
    return resp

@router.get("/{medication_id}", response_model=MedicationResponse)
def get_medication(
    profile_id: int,
    medication_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_care_profile_access(profile_id, current_user, db)
    med = db.query(Medication).filter(
        Medication.id == medication_id,
        Medication.profile_id == profile_id
    ).first()

    if not med:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medication not found")

    resp = MedicationResponse.model_validate(med)
    resp.next_dose = calculate_next_dose(med.schedule_times)
    return resp

@router.put("/{medication_id}", response_model=MedicationResponse)
def update_medication(
    profile_id: int,
    medication_id: int,
    med_in: MedicationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_care_profile_access(profile_id, current_user, db, require_write=True)
    med = db.query(Medication).filter(
        Medication.id == medication_id,
        Medication.profile_id == profile_id
    ).first()

    if not med:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medication not found")

    if med_in.name is not None:
        med.name = med_in.name
    if med_in.dosage is not None:
        med.dosage = med_in.dosage
    if med_in.form is not None:
        med.form = med_in.form
    if med_in.instructions is not None:
        med.instructions = med_in.instructions
    if med_in.schedule_times is not None:
        med.schedule_times = med_in.schedule_times
    if med_in.frequency is not None:
        med.frequency = med_in.frequency
    if med_in.start_date is not None:
        med.start_date = med_in.start_date
    if med_in.end_date is not None:
        med.end_date = med_in.end_date
    if med_in.prescribing_doctor is not None:
        med.prescribing_doctor = med_in.prescribing_doctor
    if med_in.is_active is not None:
        med.is_active = med_in.is_active

    db.commit()
    db.refresh(med)

    log_audit_event(
        db, profile_id, current_user, "MEDICATION_UPDATED",
        f"Updated medication {med.name} ({med.dosage})"
    )

    resp = MedicationResponse.model_validate(med)
    resp.next_dose = calculate_next_dose(med.schedule_times)
    return resp

@router.delete("/{medication_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_medication(
    profile_id: int,
    medication_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_care_profile_access(profile_id, current_user, db, require_write=True)
    med = db.query(Medication).filter(
        Medication.id == medication_id,
        Medication.profile_id == profile_id
    ).first()

    if not med:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medication not found")

    # Soft delete by deactivating
    med.is_active = False
    db.commit()

    log_audit_event(
        db, profile_id, current_user, "MEDICATION_DELETED",
        f"Deactivated medication {med.name}"
    )

# --- Dose Tracking & Adherence ---

@router.post("/{medication_id}/doses", response_model=DoseLogResponse, status_code=status.HTTP_201_CREATED)
def record_dose(
    profile_id: int,
    medication_id: int,
    dose_in: DoseLogCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Record a dose (taken, skipped, or missed).
    Guarantees duplicate prevention: an exact scheduled dose (medication, date, scheduled_time)
    cannot be recorded more than once.
    """
    profile = verify_care_profile_access(profile_id, current_user, db, require_write=True)
    med = db.query(Medication).filter(
        Medication.id == medication_id,
        Medication.profile_id == profile_id
    ).first()

    if not med:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medication not found")

    # PREVENT DUPLICATE DOSE RECORD
    existing_dose = db.query(DoseLog).filter(
        DoseLog.medication_id == medication_id,
        DoseLog.scheduled_date == dose_in.scheduled_date,
        DoseLog.scheduled_time == dose_in.scheduled_time
    ).first()

    if existing_dose:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Dose for {med.name} on {dose_in.scheduled_date} at {dose_in.scheduled_time} is already recorded as '{existing_dose.status.value}'."
        )

    log = DoseLog(
        medication_id=medication_id,
        profile_id=profile_id,
        recorded_by_id=current_user.id,
        scheduled_date=dose_in.scheduled_date,
        scheduled_time=dose_in.scheduled_time,
        recorded_at=datetime.now(timezone.utc),
        status=dose_in.status,
        notes=dose_in.notes
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    log_audit_event(
        db, profile_id, current_user, "DOSE_RECORDED",
        f"Marked dose of {med.name} at {dose_in.scheduled_time} as {dose_in.status.value.upper()}"
    )

    # If missed, optionally notify care circle/family
    if dose_in.status == DoseStatus.MISSED:
        ref_key = f"missed_alert:{med.id}:{dose_in.scheduled_date}:{dose_in.scheduled_time}"
        profile_owner = db.query(User).filter(User.id == profile.owner_id).first()
        if profile_owner and profile_owner.email:
            EmailService.send_email(
                db=db,
                profile_id=profile_id,
                recipient_email=profile_owner.email,
                subject=f"ALERT: Missed dose of {med.name} for {profile.full_name}",
                html_content=format_missed_dose_alert_email(
                    profile.full_name, med.name, med.dosage, dose_in.scheduled_time
                ),
                notification_type="missed_dose_alert",
                reference_key=ref_key,
                user_id=profile_owner.id
            )

    return DoseLogResponse(
        id=log.id,
        medication_id=log.medication_id,
        medication_name=med.name,
        profile_id=log.profile_id,
        recorded_by_id=log.recorded_by_id,
        recorded_by_name=current_user.full_name,
        scheduled_date=log.scheduled_date,
        scheduled_time=log.scheduled_time,
        recorded_at=log.recorded_at,
        status=log.status,
        notes=log.notes
    )

@router.get("/doses/history", response_model=List[DoseLogResponse])
def get_adherence_history(
    profile_id: int,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_care_profile_access(profile_id, current_user, db)
    doses = db.query(DoseLog).filter(
        DoseLog.profile_id == profile_id
    ).order_by(DoseLog.recorded_at.desc()).limit(limit).all()

    result = []
    for d in doses:
        med = db.query(Medication).filter(Medication.id == d.medication_id).first()
        user = db.query(User).filter(User.id == d.recorded_by_id).first()
        result.append(DoseLogResponse(
            id=d.id,
            medication_id=d.medication_id,
            medication_name=med.name if med else "Unknown",
            profile_id=d.profile_id,
            recorded_by_id=d.recorded_by_id,
            recorded_by_name=user.full_name if user else "Care Circle",
            scheduled_date=d.scheduled_date,
            scheduled_time=d.scheduled_time,
            recorded_at=d.recorded_at,
            status=d.status,
            notes=d.notes
        ))
    return result
