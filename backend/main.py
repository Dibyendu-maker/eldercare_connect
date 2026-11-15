from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from backend.config import settings
from backend.database import engine, Base
from backend.routers import (
    auth, profiles, medications, appointments, 
    health, circle, dashboard, notifications
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all database tables automatically on startup
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Collaborative elderly medication and healthcare management platform.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Enable CORS with explicit allowed origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all API routers under settings.API_V1_PREFIX (/api)
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(profiles.router, prefix=settings.API_V1_PREFIX)
app.include_router(medications.router, prefix=settings.API_V1_PREFIX)
app.include_router(appointments.router, prefix=settings.API_V1_PREFIX)
app.include_router(health.router, prefix=settings.API_V1_PREFIX)
app.include_router(circle.router, prefix=settings.API_V1_PREFIX)
app.include_router(dashboard.router, prefix=settings.API_V1_PREFIX)
app.include_router(notifications.router, prefix=settings.API_V1_PREFIX)

@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "database": "connected"
    }

@app.get("/", tags=["System"])
def root():
    return {
        "message": "Welcome to ElderCare Connect API. Visit /docs for full interactive API documentation.",
        "documentation": "/docs"
    }
