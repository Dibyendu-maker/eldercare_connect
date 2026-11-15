import pytest
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.main import app
from backend.models import User, ElderlyProfile, UserRole, HealthProfile
from backend.security import hash_password

# Use in-memory SQLite with StaticPool for high-speed, thread-safe tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def elderly_user_token(client):
    res = client.post("/api/auth/register", json={
        "email": "elderly.alice@care.org",
        "password": "Password123!",
        "full_name": "Alice Cooper",
        "phone": "+1-555-0101",
        "role": "elderly"
    })
    assert res.status_code == 201
    data = res.json()
    token = data["access_token"]
    
    # Get profile id
    prof_res = client.get("/api/profiles", headers={"Authorization": f"Bearer {token}"})
    assert prof_res.status_code == 200
    profile_id = prof_res.json()[0]["id"]
    
    return {
        "token": token,
        "user": data["user"],
        "profile_id": profile_id
    }

@pytest.fixture
def family_user_token(client):
    res = client.post("/api/auth/register", json={
        "email": "family.bob@care.org",
        "password": "Password123!",
        "full_name": "Bob Cooper",
        "phone": "+1-555-0102",
        "role": "family"
    })
    assert res.status_code == 201
    data = res.json()
    return {
        "token": data["access_token"],
        "user": data["user"]
    }

@pytest.fixture
def caretaker_user_token(client):
    res = client.post("/api/auth/register", json={
        "email": "nurse.clara@care.org",
        "password": "Password123!",
        "full_name": "Clara Nurse",
        "phone": "+1-555-0103",
        "role": "caretaker"
    })
    assert res.status_code == 201
    data = res.json()
    return {
        "token": data["access_token"],
        "user": data["user"]
    }

@pytest.fixture
def unrelated_user_token(client):
    res = client.post("/api/auth/register", json={
        "email": "stranger.dan@other.org",
        "password": "Password123!",
        "full_name": "Dan Stranger",
        "phone": "+1-555-9999",
        "role": "family"
    })
    assert res.status_code == 201
    data = res.json()
    return {
        "token": data["access_token"],
        "user": data["user"]
    }
