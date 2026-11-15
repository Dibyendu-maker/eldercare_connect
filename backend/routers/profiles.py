from typing import List
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    User, ElderlyProfile, CareCircleMember, CareCircleInvite, 
    HealthProfile, UserRole
)
from backend.schemas import (
    ElderlyProfileCreate, ElderlyProfileUpdate, ElderlyProfileResponse,
    CareCircleInviteCreate, CareCircleInviteResponse, CareCircleAcceptInvite,
    CareCircleMemberResponse
)
from backend.security import (
    get_current_user, verify_care_profile_access, generate_secure_passcode
)
from backend.audit import log_audit_event
from backend.config import settings

router = APIRouter(prefix="/profiles", tags=["Elderly Care Profiles & Invites"])

@router.get("", response_model=List[ElderlyProfileResponse])
def list_accessible_profiles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns all elderly care profiles current_user has authorized access to:
    1. Profiles owned by the user
    2. Profiles where user is an authorized active member of the Care Circle
    """
    owned = db.query(ElderlyProfile).filter(ElderlyProfile.owner_id == current_user.id).all()
    
    # Care circle memberships
    memberships = db.query(CareCircleMember).filter(
        CareCircleMember.user_id == current_user.id,
        CareCircleMember.is_active == True
    ).all()
    member_profile_ids = [m.profile_id for m in memberships]
    
    circle_profiles = db.query(ElderlyProfile).filter(
        ElderlyProfile.id.in_(member_profile_ids),
        ElderlyProfile.owner_id != current_user.id
    ).all() if member_profile_ids else []

    return owned + circle_profiles

@router.post("", response_model=ElderlyProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(
    profile_in: ElderlyProfileCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile = ElderlyProfile(
        owner_id=current_user.id,
        full_name=profile_in.full_name,
        date_of_birth=profile_in.date_of_birth,
        primary_phone=profile_in.primary_phone,
        address=profile_in.address,
        emergency_notes=profile_in.emergency_notes
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    # Initialize associated 1-to-1 HealthProfile
    health = HealthProfile(
        profile_id=profile.id,
        allergies=[],
        emergency_contacts=[],
        medical_conditions=[]
    )
    db.add(health)
    db.commit()

    log_audit_event(
        db, profile.id, current_user, "PROFILE_CREATED",
        f"Elderly care profile created for {profile.full_name}"
    )

    return profile

@router.get("/{profile_id}", response_model=ElderlyProfileResponse)
def get_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile = verify_care_profile_access(profile_id, current_user, db)
    return profile

@router.put("/{profile_id}", response_model=ElderlyProfileResponse)
def update_profile(
    profile_id: int,
    profile_in: ElderlyProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile = verify_care_profile_access(profile_id, current_user, db, require_write=True)
    
    if profile_in.full_name is not None:
        profile.full_name = profile_in.full_name
    if profile_in.date_of_birth is not None:
        profile.date_of_birth = profile_in.date_of_birth
    if profile_in.primary_phone is not None:
        profile.primary_phone = profile_in.primary_phone
    if profile_in.address is not None:
        profile.address = profile_in.address
    if profile_in.emergency_notes is not None:
        profile.emergency_notes = profile_in.emergency_notes
        
    db.commit()
    db.refresh(profile)

    log_audit_event(
        db, profile.id, current_user, "PROFILE_UPDATED",
        f"Elderly profile details updated"
    )

    return profile

# --- Care Circle Invitation Management ---

@router.post("/{profile_id}/invites", response_model=CareCircleInviteResponse, status_code=status.HTTP_201_CREATED)
def create_invite_passcode(
    profile_id: int,
    invite_in: CareCircleInviteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generates an expiring 8-character passcode to invite a family member or caretaker.
    Requires profile owner authorization.
    """
    profile = verify_care_profile_access(profile_id, current_user, db, require_owner=True)

    passcode = generate_secure_passcode(8)
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.INVITE_EXPIRY_HOURS)

    invite = CareCircleInvite(
        profile_id=profile.id,
        created_by_id=current_user.id,
        invite_code=passcode,
        intended_role=invite_in.intended_role,
        intended_relationship=invite_in.intended_relationship,
        permissions=invite_in.permissions,
        expires_at=expires,
        is_used=False
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    log_audit_event(
        db, profile.id, current_user, "INVITE_GENERATED",
        f"Generated expiring invite code for role {invite_in.intended_role.value} ({invite_in.intended_relationship})"
    )

    return invite

@router.get("/{profile_id}/invites", response_model=List[CareCircleInviteResponse])
def list_profile_invites(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    verify_care_profile_access(profile_id, current_user, db, require_owner=True)
    invites = db.query(CareCircleInvite).filter(
        CareCircleInvite.profile_id == profile_id,
        CareCircleInvite.is_used == False
    ).order_by(CareCircleInvite.created_at.desc()).all()
    return invites

@router.post("/join", response_model=CareCircleMemberResponse)
def accept_invite_passcode(
    accept_in: CareCircleAcceptInvite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Accept an invitation passcode to join an elderly person's care circle.
    Validates expiration and prevents multiple redemptions.
    """
    code = accept_in.invite_code.strip().upper()
    invite = db.query(CareCircleInvite).filter(
        CareCircleInvite.invite_code == code
    ).first()

    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid invitation passcode.")

    if invite.is_used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This invitation passcode has already been used.")

    # Check expiration (compare UTC)
    now = datetime.now(timezone.utc)
    # Ensure invite.expires_at is timezone-aware
    expires_at = invite.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if now > expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This invitation passcode has expired.")

    # Check if already a member or owner
    profile = db.query(ElderlyProfile).filter(ElderlyProfile.id == invite.profile_id).first()
    if profile.owner_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are already the owner of this care profile.")

    existing_member = db.query(CareCircleMember).filter(
        CareCircleMember.profile_id == invite.profile_id,
        CareCircleMember.user_id == current_user.id
    ).first()

    if existing_member:
        if existing_member.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are already an active member of this Care Circle.")
        else:
            # Reactivate
            existing_member.is_active = True
            existing_member.role = invite.intended_role
            existing_member.relationship = invite.intended_relationship
            existing_member.permissions = invite.permissions
            member = existing_member
    else:
        member = CareCircleMember(
            profile_id=invite.profile_id,
            user_id=current_user.id,
            relationship=invite.intended_relationship,
            role=invite.intended_role,
            permissions=invite.permissions,
            is_active=True
        )
        db.add(member)

    # Mark invite as used
    invite.is_used = True
    invite.used_by_id = current_user.id

    db.commit()
    db.refresh(member)

    log_audit_event(
        db, invite.profile_id, current_user, "CARE_CIRCLE_JOINED",
        f"{current_user.full_name} joined Care Circle as {invite.intended_relationship} ({invite.intended_role.value})"
    )

    return CareCircleMemberResponse(
        id=member.id,
        profile_id=member.profile_id,
        user_id=member.user_id,
        user_name=current_user.full_name,
        user_email=current_user.email,
        relationship=member.relationship,
        role=member.role,
        permissions=member.permissions,
        is_active=member.is_active,
        joined_at=member.joined_at
    )
