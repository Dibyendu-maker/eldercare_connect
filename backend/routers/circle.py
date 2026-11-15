from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, ElderlyProfile, CareCircleMember, AuditLog
from backend.schemas import CareCircleMemberResponse, AuditLogResponse
from backend.security import get_current_user, verify_care_profile_access
from backend.audit import log_audit_event

router = APIRouter(prefix="/profiles/{profile_id}/circle", tags=["Care Circle Management & Audit"])

@router.get("/members", response_model=List[CareCircleMemberResponse])
def list_care_circle_members(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_care_profile_access(profile_id, current_user, db)
    members = db.query(CareCircleMember).filter(
        CareCircleMember.profile_id == profile_id,
        CareCircleMember.is_active == True
    ).all()

    result = []
    for m in members:
        u = db.query(User).filter(User.id == m.user_id).first()
        result.append(CareCircleMemberResponse(
            id=m.id,
            profile_id=m.profile_id,
            user_id=m.user_id,
            user_name=u.full_name if u else "Unknown",
            user_email=u.email if u else "unknown@care.org",
            relationship=m.relationship,
            role=m.role,
            permissions=m.permissions,
            is_active=m.is_active,
            joined_at=m.joined_at
        ))
    return result

@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_care_circle_member(
    profile_id: int,
    member_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Revoke a member from the care circle.
    Only the profile owner has authorization to revoke access.
    """
    profile = verify_care_profile_access(profile_id, current_user, db, require_owner=True)
    member = db.query(CareCircleMember).filter(
        CareCircleMember.id == member_id,
        CareCircleMember.profile_id == profile_id
    ).first()

    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Care circle member not found")

    revoked_user = db.query(User).filter(User.id == member.user_id).first()
    revoked_name = revoked_user.full_name if revoked_user else f"User #{member.user_id}"

    member.is_active = False
    db.commit()

    log_audit_event(
        db, profile_id, current_user, "MEMBER_REVOKED",
        f"Revoked {revoked_name} from Care Circle"
    )

@router.get("/audit", response_model=List[AuditLogResponse])
def get_audit_trail(
    profile_id: int,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_care_profile_access(profile_id, current_user, db)
    logs = db.query(AuditLog).filter(
        AuditLog.profile_id == profile_id
    ).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return logs
