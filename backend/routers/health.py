from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, HealthProfile, ElderlyProfile
from backend.schemas import HealthProfileUpdate, HealthProfileResponse
from backend.security import get_current_user, verify_care_profile_access
from backend.audit import log_audit_event

router = APIRouter(prefix="/profiles/{profile_id}/health", tags=["Emergency Health Profile"])

@router.get("", response_model=HealthProfileResponse)
def get_health_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_care_profile_access(profile_id, current_user, db)
    health = db.query(HealthProfile).filter(HealthProfile.profile_id == profile_id).first()
    
    if not health:
        # Create empty if not initialized
        health = HealthProfile(
            profile_id=profile_id,
            allergies=[],
            emergency_contacts=[],
            medical_conditions=[]
        )
        db.add(health)
        db.commit()
        db.refresh(health)

    return health

@router.put("", response_model=HealthProfileResponse)
def update_health_profile(
    profile_id: int,
    health_in: HealthProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_care_profile_access(profile_id, current_user, db, require_write=True)
    health = db.query(HealthProfile).filter(HealthProfile.profile_id == profile_id).first()

    if not health:
        health = HealthProfile(profile_id=profile_id)
        db.add(health)

    if health_in.blood_type is not None:
        health.blood_type = health_in.blood_type
    if health_in.allergies is not None:
        health.allergies = health_in.allergies
    if health_in.emergency_contacts is not None:
        health.emergency_contacts = [c.model_dump() for c in health_in.emergency_contacts]
    if health_in.medical_conditions is not None:
        health.medical_conditions = health_in.medical_conditions
    if health_in.emergency_notes is not None:
        health.emergency_notes = health_in.emergency_notes

    db.commit()
    db.refresh(health)

    log_audit_event(
        db, profile_id, current_user, "HEALTH_PROFILE_UPDATED",
        "Emergency health profile and contacts updated"
    )

    return health
