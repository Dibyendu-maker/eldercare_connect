import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import httpx
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import NotificationLog, NotificationStatus

logger = logging.getLogger(__name__)

class EmailService:
    @staticmethod
    def get_status() -> Dict[str, Any]:
        has_key = bool(settings.RESEND_API_KEY and len(settings.RESEND_API_KEY.strip()) > 0)
        return {
            "configured": has_key,
            "provider": "Resend",
            "sender_address": settings.EMAIL_FROM,
            "status_message": (
                "Resend API is connected and active." 
                if has_key else 
                "Resend API key not provided in environment variables. System operates in transparent mock mode: logs notifications without sending."
            )
        }

    @staticmethod
    def send_email(
        db: Session,
        profile_id: int,
        recipient_email: str,
        subject: str,
        html_content: str,
        notification_type: str,
        reference_key: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Sends an email via Resend API or logs transparently if unconfigured.
        Prevents duplicate notifications if reference_key is provided.
        Never claims an email was sent via Resend if it wasn't.
        """
        # 1. Duplicate check
        if reference_key:
            existing = db.query(NotificationLog).filter(
                NotificationLog.reference_key == reference_key,
                NotificationLog.status.in_([NotificationStatus.SENT, NotificationStatus.MOCKED_NO_KEY])
            ).first()
            if existing:
                logger.info(f"Duplicate notification prevented for reference_key: {reference_key}")
                return {
                    "sent": False,
                    "status": "duplicate_skipped",
                    "reference_key": reference_key,
                    "message": "Notification already dispatched for this event."
                }

        has_api_key = bool(settings.RESEND_API_KEY and len(settings.RESEND_API_KEY.strip()) > 0)

        # 2. Transparent handling when Resend key is missing
        if not has_api_key:
            log_entry = NotificationLog(
                profile_id=profile_id,
                user_id=user_id,
                notification_type=notification_type,
                recipient_email=recipient_email,
                subject=subject,
                message=html_content[:500],
                status=NotificationStatus.MOCKED_NO_KEY,
                external_id=None,
                reference_key=reference_key,
                sent_at=datetime.now(timezone.utc)
            )
            db.add(log_entry)
            db.commit()
            return {
                "sent": False,
                "status": "mocked_no_key",
                "reference_key": reference_key,
                "message": "Resend API key not configured. Event recorded in audit notification log without sending."
            }

        # 3. Call Resend API
        headers = {
            "Authorization": f"Bearer {settings.RESEND_API_KEY.strip()}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": settings.EMAIL_FROM,
            "to": [recipient_email],
            "subject": subject,
            "html": html_content
        }

        try:
            with httpx.Client(timeout=8.0) as client:
                response = client.post(
                    "https://api.resend.com/emails",
                    headers=headers,
                    json=payload
                )
            
            if response.status_code in (200, 201):
                res_data = response.json()
                ext_id = res_data.get("id", "resend_ok")
                log_entry = NotificationLog(
                    profile_id=profile_id,
                    user_id=user_id,
                    notification_type=notification_type,
                    recipient_email=recipient_email,
                    subject=subject,
                    message=html_content[:500],
                    status=NotificationStatus.SENT,
                    external_id=ext_id,
                    reference_key=reference_key,
                    sent_at=datetime.now(timezone.utc)
                )
                db.add(log_entry)
                db.commit()
                return {
                    "sent": True,
                    "status": "sent",
                    "external_id": ext_id,
                    "reference_key": reference_key,
                    "message": "Email successfully sent via Resend."
                }
            else:
                error_body = response.text
                logger.error(f"Resend API error {response.status_code}: {error_body}")
                log_entry = NotificationLog(
                    profile_id=profile_id,
                    user_id=user_id,
                    notification_type=notification_type,
                    recipient_email=recipient_email,
                    subject=subject,
                    message=f"Failed with {response.status_code}: {error_body}"[:500],
                    status=NotificationStatus.FAILED,
                    external_id=None,
                    reference_key=reference_key,
                    sent_at=datetime.now(timezone.utc)
                )
                db.add(log_entry)
                db.commit()
                return {
                    "sent": False,
                    "status": "failed",
                    "error": error_body,
                    "message": f"Resend API rejected request: {response.status_code}"
                }

        except Exception as exc:
            logger.error(f"Failed to communicate with Resend: {exc}")
            log_entry = NotificationLog(
                profile_id=profile_id,
                user_id=user_id,
                notification_type=notification_type,
                recipient_email=recipient_email,
                subject=subject,
                message=f"Exception: {str(exc)}"[:500],
                status=NotificationStatus.FAILED,
                external_id=None,
                reference_key=reference_key,
                sent_at=datetime.now(timezone.utc)
            )
            db.add(log_entry)
            db.commit()
            return {
                "sent": False,
                "status": "failed",
                "error": str(exc),
                "message": "Network or connection error communicating with Resend."
            }

def format_medication_reminder_email(elderly_name: str, med_name: str, dosage: str, instructions: str, scheduled_time: str) -> str:
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <div style="background-color: #0f172a; color: white; padding: 16px; border-radius: 6px; margin-bottom: 20px;">
            <h2 style="margin: 0; font-size: 20px;">ElderCare Connect</h2>
            <p style="margin: 4px 0 0 0; font-size: 14px; opacity: 0.9;">Upcoming Medication Reminder</p>
        </div>
        <p style="font-size: 16px; color: #1e293b;">Hello,</p>
        <p style="font-size: 15px; color: #334155;">
            This is a scheduled reminder for <strong>{elderly_name}</strong> to take their medication:
        </p>
        <div style="background-color: #f8fafc; border-left: 4px solid #0d9488; padding: 16px; margin: 20px 0; border-radius: 4px;">
            <p style="margin: 0 0 8px 0; font-size: 18px; font-weight: bold; color: #0f172a;">{med_name} ({dosage})</p>
            <p style="margin: 0 0 8px 0; font-size: 14px; color: #475569;"><strong>Scheduled Time:</strong> {scheduled_time}</p>
            <p style="margin: 0; font-size: 14px; color: #475569;"><strong>Instructions:</strong> {instructions or 'Take as directed'}</p>
        </div>
        <p style="font-size: 14px; color: #64748b;">
            Please open ElderCare Connect to confirm the dose once taken.
        </p>
        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
        <p style="font-size: 12px; color: #94a3b8; margin: 0;">
            ElderCare Connect &bull; Collaborative Healthcare Management &bull; Confidential
        </p>
    </div>
    """

def format_missed_dose_alert_email(elderly_name: str, med_name: str, dosage: str, scheduled_time: str) -> str:
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #fee2e2; border-radius: 8px;">
        <div style="background-color: #b91c1c; color: white; padding: 16px; border-radius: 6px; margin-bottom: 20px;">
            <h2 style="margin: 0; font-size: 20px;">ElderCare Connect</h2>
            <p style="margin: 4px 0 0 0; font-size: 14px; opacity: 0.9;">Missed Medication Alert</p>
        </div>
        <p style="font-size: 16px; color: #1e293b;">Care Circle Alert,</p>
        <p style="font-size: 15px; color: #334155;">
            A scheduled dose for <strong>{elderly_name}</strong> was marked as <strong>MISSED</strong> or remained unconfirmed past the scheduled window:
        </p>
        <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 16px; margin: 20px 0; border-radius: 4px;">
            <p style="margin: 0 0 8px 0; font-size: 18px; font-weight: bold; color: #991b1b;">{med_name} ({dosage})</p>
            <p style="margin: 0; font-size: 14px; color: #7f1d1d;"><strong>Scheduled Time:</strong> {scheduled_time}</p>
        </div>
        <p style="font-size: 14px; color: #64748b;">
            Please check in with {elderly_name} to ensure health and safety.
        </p>
        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
        <p style="font-size: 12px; color: #94a3b8; margin: 0;">
            ElderCare Connect &bull; Care Circle Safety Monitoring
        </p>
    </div>
    """

def format_appointment_reminder_email(elderly_name: str, doctor: str, specialty: str, date: str, time: str, location: str) -> str:
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <div style="background-color: #0f172a; color: white; padding: 16px; border-radius: 6px; margin-bottom: 20px;">
            <h2 style="margin: 0; font-size: 20px;">ElderCare Connect</h2>
            <p style="margin: 4px 0 0 0; font-size: 14px; opacity: 0.9;">Upcoming Healthcare Appointment</p>
        </div>
        <p style="font-size: 16px; color: #1e293b;">Hello,</p>
        <p style="font-size: 15px; color: #334155;">
            This is a reminder of an upcoming medical appointment for <strong>{elderly_name}</strong>:
        </p>
        <div style="background-color: #f8fafc; border-left: 4px solid #3b82f6; padding: 16px; margin: 20px 0; border-radius: 4px;">
            <p style="margin: 0 0 8px 0; font-size: 18px; font-weight: bold; color: #0f172a;">Dr. {doctor} ({specialty})</p>
            <p style="margin: 0 0 8px 0; font-size: 14px; color: #475569;"><strong>Date & Time:</strong> {date} at {time}</p>
            <p style="margin: 0; font-size: 14px; color: #475569;"><strong>Location:</strong> {location}</p>
        </div>
        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
        <p style="font-size: 12px; color: #94a3b8; margin: 0;">
            ElderCare Connect &bull; Collaborative Healthcare Management
        </p>
    </div>
    """
