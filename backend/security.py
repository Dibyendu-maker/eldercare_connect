import base64
import hashlib
import hmac
import json
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

from backend.config import settings
from backend.database import get_db
from backend.models import User, ElderlyProfile, CareCircleMember, UserRole

# Password Hasher
pwd_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19456,  # 19 MiB
    parallelism=1,
    hash_len=32,
    salt_len=16
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")

def hash_password(password: str) -> str:
    return pwd_hasher.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False

# Base64URL helper
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def _b64url_decode(data_str: str) -> bytes:
    padding = '=' * (4 - (len(data_str) % 4)) if len(data_str) % 4 != 0 else ''
    return base64.urlsafe_b64decode((data_str + padding).encode('utf-8'))

# Standard HS256 JWT Token creation
def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp())
    })
    
    header = {"alg": "HS256", "typ": "JWT"}
    header_bytes = json.dumps(header, separators=(',', ':')).encode('utf-8')
    payload_bytes = json.dumps(to_encode, separators=(',', ':')).encode('utf-8')
    
    header_b64 = _b64url_encode(header_bytes)
    payload_b64 = _b64url_encode(payload_bytes)
    
    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    key_bytes = settings.SECRET_KEY.encode('utf-8')
    signature = hmac.new(key_bytes, signing_input, hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)
    
    return f"{header_b64}.{payload_b64}.{signature_b64}"

# Standard HS256 JWT Token verification
def decode_access_token(token: str) -> Dict[str, Any]:
    parts = token.split('.')
    if len(parts) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token structure",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    header_b64, payload_b64, signature_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    key_bytes = settings.SECRET_KEY.encode('utf-8')
    expected_sig = hmac.new(key_bytes, signing_input, hashlib.sha256).digest()
    
    try:
        actual_sig = _b64url_decode(signature_b64)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Corrupted token signature",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload_json = _b64url_decode(payload_b64).decode('utf-8')
        payload = json.loads(payload_json)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check expiration
    exp = payload.get("exp")
    if exp is not None:
        if datetime.now(timezone.utc).timestamp() > exp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
    return payload

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception
    try:
        user_id = int(user_id_str)
    except ValueError:
        raise credentials_exception
        
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if user is None:
        raise credentials_exception
    return user

def generate_secure_passcode(length: int = 8) -> str:
    """Generate a clean, readable expiring invite passcode (alphanumeric uppercase/digits without ambiguous characters)"""
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # avoids 0, O, 1, I
    return "".join(secrets.choice(alphabet) for _ in range(length))

def verify_care_profile_access(
    profile_id: int, 
    current_user: User, 
    db: Session,
    require_owner: bool = False,
    require_write: bool = False
) -> ElderlyProfile:
    """
    Enforces multi-tenant care-circle profile isolation.
    Returns ElderlyProfile if current_user is owner or authorized care circle member.
    Otherwise raises HTTP 403 Forbidden.
    """
    profile = db.query(ElderlyProfile).filter(ElderlyProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Elderly care profile not found")
        
    # Check if user is the direct owner
    if profile.owner_id == current_user.id:
        return profile
        
    if require_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Action requires profile owner permissions"
        )
        
    # Check if user is an active member of the care circle
    membership = db.query(CareCircleMember).filter(
        CareCircleMember.profile_id == profile_id,
        CareCircleMember.user_id == current_user.id,
        CareCircleMember.is_active == True
    ).first()
    
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Access denied: You are not an authorized member of this care circle"
        )
        
    if require_write and membership.permissions == "read_only":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You have read-only access to this profile"
        )
        
    return profile
