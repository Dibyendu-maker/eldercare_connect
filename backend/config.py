import os
from typing import Optional, List
from pydantic import BaseModel

class Settings(BaseModel):
    PROJECT_NAME: str = "ElderCare Connect"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api"
    
    # Internal Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "sqlite:///./eldercare_connect.db"
    )
    
    # JWT & Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "eldercare-local-dev-secret-key-do-not-use-in-production-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # CORS: Restrict to explicit origins instead of wildcard in production
    ALLOWED_ORIGINS: List[str] = [
        origin.strip()
        for origin in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    ]
    
    # Resend Email Integration
    RESEND_API_KEY: Optional[str] = os.getenv("RESEND_API_KEY", None)
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "ElderCare Connect <notifications@eldercareconnect.org>")
    
    # Care Circle
    INVITE_EXPIRY_HOURS: int = 48

    def __init__(self, **values):
        super().__init__(**values)
        if self.ENVIRONMENT.lower() == "production":
            insecure_defaults = [
                "eldercare-super-secret-production-key-2026-secure-token",
                "eldercare-local-dev-secret-key-do-not-use-in-production-2026",
                "change-me",
                "secret",
                "password",
                ""
            ]
            if not self.SECRET_KEY or self.SECRET_KEY in insecure_defaults:
                raise ValueError(
                    "CRITICAL SECURITY CONFIGURATION ERROR: SECRET_KEY environment variable "
                    "must be explicitly set to a strong, high-entropy secret in production mode."
                )

settings = Settings()
