from sqlalchemy.orm import Session
from backend.models import AuditLog, User

def log_audit_event(
    db: Session,
    profile_id: int,
    user: User,
    action: str,
    details: str
):
    try:
        audit_entry = AuditLog(
            profile_id=profile_id,
            user_id=user.id,
            user_name=user.full_name,
            action=action,
            details=details
        )
        db.add(audit_entry)
        db.commit()
    except Exception as e:
        db.rollback()
        # Logging failure shouldn't crash the transaction
        print(f"[AUDIT LOG ERROR] Failed to record audit log: {e}")
