
import base64
import hashlib
import hmac
import json
import math
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

from backend.config import settings
from backend.database import get_db
from backend.models import User, ElderlyProfile, CareCircleMember

pwd_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19456,
    parallelism=1,
    hash_len=32,
    salt_len=16
)

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login"
)

def hash_password(password: str) -> str:
    return pwd_hasher.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False

def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")

def _b64url_decode(data_str: str) -> bytes:
    if not isinstance(data_str, str) or not data_str:
        raise ValueError("Invalid Base64URL segment")

    padding = "=" * (-len(data_str) % 4)
    return base64.b64decode(
        (data_str + padding).encode("ascii"),
        altchars=b"-_",
        validate=True
    )

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    to_encode.update({
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp())
    })

    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    payload_b64 = _b64url_encode(
        json.dumps(to_encode, separators=(",", ":")).encode("utf-8")
    )

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        signing_input,
        hashlib.sha256
    ).digest()

    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"

def decode_access_token(token: str) -> Dict[str, Any]:
    if not isinstance(token, str):
        raise _unauthorized("Invalid authentication token structure")

    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise _unauthorized("Invalid authentication token structure")

    header_b64, payload_b64, signature_b64 = parts

    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        actual_signature = _b64url_decode(signature_b64)
    except (ValueError, UnicodeDecodeError, TypeError):
        raise _unauthorized("Malformed authentication token")

    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise _unauthorized("Unsupported token algorithm")

    if "typ" in header and header["typ"] != "JWT":
        raise _unauthorized("Invalid token type")

    if not isinstance(payload, dict):
        raise _unauthorized("Malformed token payload")

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        signing_input,
        hashlib.sha256
    ).digest()

    if not hmac.compare_digest(expected_signature, actual_signature):
        raise _unauthorized("Invalid token signature")

    exp = payload.get("exp")

    if (
        isinstance(exp, bool)
        or not isinstance(exp, (int, float))
        or not math.isfinite(exp)
    ):
        raise _unauthorized("Token expiration is missing or invalid")

    if datetime.now(timezone.utc).timestamp() >= exp:
        raise _unauthorized("Token has expired. Please log in again.")

    return payload

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = _unauthorized("Could not validate credentials")

    payload = decode_access_token(token)
    user_id_str = payload.get("sub")

    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise credentials_exception

    user = db.query(User).filter(
        User.id == user_id,
        User.is_active == True
    ).first()

    if user is None:
        raise credentials_exception

    return user

def generate_secure_passcode(length: int = 8) -> str:
    """Generate a readable alphanumeric care-circle invite passcode."""
    if isinstance(length, bool) or not isinstance(length, int) or length < 1:
        raise ValueError("Passcode length must be a positive integer")

    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(secrets.choice(alphabet) for _ in range(length))

def verify_care_profile_access(
    profile_id: int,
    current_user: User,
    db: Session,
    require_owner: bool = False,
    require_write: bool = False
) -> ElderlyProfile:
    """
    Enforce multi-tenant care-circle profile isolation.
    Only the owner or an authorized active member can access a profile.
    """
    profile = db.query(ElderlyProfile).filter(
        ElderlyProfile.id == profile_id
    ).first()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Elderly care profile not found"
        )

    if profile.owner_id == current_user.id:
        return profile

    if require_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action requires profile owner permissions"
        )

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