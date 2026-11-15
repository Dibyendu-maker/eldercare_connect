from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from backend.database import get_db
from backend.models import User, ElderlyProfile, HealthProfile, UserRole
from backend.schemas import UserCreate, UserLogin, UserResponse, TokenResponse
from backend.security import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    # Check if email is already registered
    existing_user = db.query(User).filter(User.email == user_in.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists."
        )

    # Hash credentials securely using Argon2
    hashed_pwd = hash_password(user_in.password)
    
    new_user = User(
        email=user_in.email.lower(),
        hashed_password=hashed_pwd,
        full_name=user_in.full_name,
        phone=user_in.phone,
        role=user_in.role,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # If the user is an Elderly individual, automatically create their primary care profile and health profile
    if new_user.role == UserRole.ELDERLY:
        profile = ElderlyProfile(
            owner_id=new_user.id,
            full_name=new_user.full_name,
            primary_phone=new_user.phone,
            emergency_notes="Primary emergency care profile created upon registration."
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        health = HealthProfile(
            profile_id=profile.id,
            allergies=[],
            emergency_contacts=[],
            medical_conditions=[]
        )
        db.add(health)
        db.commit()

    # Generate JWT
    token = create_access_token(data={
        "sub": str(new_user.id),
        "email": new_user.email,
        "role": new_user.role.value
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": new_user
    }

@router.post("/login", response_model=TokenResponse)
def login(login_in: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_in.email.lower()).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(login_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated."
        )

    token = create_access_token(data={
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user
    }

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
