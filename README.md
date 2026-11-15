# ElderCare Connect

> A collaborative, secure, and multi-tenant elderly healthcare and medication management platform built with FastAPI, SQLAlchemy, and Argon2.

---

## Overview

**ElderCare Connect** is designed to address the challenges of elderly care coordination. It bridges the communication gap between elderly individuals, their family members, and professional caretakers by providing:
- **Medication Schedule & Adherence Tracking**: Prevents duplicate dose logging and tracks real-time adherence.
- **Dynamic Dashboard**: Aggregates today's medications, upcoming appointments, care circle contacts, and recent audit activity.
- **Healthcare Appointments**: Schedule, update, and dispatch reminders with built-in duplicate prevention.
- **Care Circle Coordination**: Multi-tenant, consent-driven access using secure, unambiguous, expiring passcodes.
- **Emergency Health Profile**: Instant access to blood type, allergies, conditions, and prioritized emergency contacts.
- **Transparent Notifications**: Resend email integration with automatic duplicate prevention and honest offline mock mode when API keys are unconfigured.

---

## Technology Stack

- **Backend Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+)
- **ORM & Database**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/) with SQLite (local development / testing) and PostgreSQL support (production).
- **Data Validation & Serialization**: [Pydantic v2](https://docs.pydantic.dev/) with `ConfigDict` and typed schemas.
- **Credential Hashing**: **Argon2id** via `argon2-cffi` (memory-hard, GPU/ASIC attack resistant).
- **Authentication**: Stateless HS256 JWT tokens with HMAC-SHA256 signature verification.
- **Testing**: [pytest](https://docs.pytest.org/) with `StaticPool` in-memory SQLite isolation.
- **Email Service**: Resend API integration with duplicate suppression and fallback mock logging.

---

## Architecture & Security Model

```
                    ┌─────────────────────────┐
                    │    Client Applications  │
                    │  (Web / Mobile Clients) │
                    └────────────┬────────────┘
                                 │ REST API (Bearer JWT)
                                 ▼
                    ┌─────────────────────────┐
                    │     FastAPI Gateway     │
                    │   CORS / Auth / Lifespan │
                    └────────────┬────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Authentication  │    │  Care Circle &   │    │  Medications &   │
│ & Access Control │    │   Appointments   │    │  Adherence Logs  │
│  (Argon2 / JWT)  │    │ (Tenant Boundary)│    │(Deduplication)   │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │     SQLAlchemy ORM      │
                    │ (PostgreSQL / SQLite)   │
                    └────────────┬────────────┘
                                 │
         ┌───────────────────────┴───────────────────────┐
         ▼                                               ▼
┌──────────────────┐                            ┌──────────────────┐
│ Audit Trail Logs │                            │  Email Service   │
│ (Every Mutation) │                            │ (Resend / Mock)  │
└──────────────────┘                            └──────────────────┘
```

### Key Security Safeguards
1. **Multi-Tenant Profile Isolation**: Enforced by `verify_care_profile_access()`. Unrelated users receive HTTP 403 Forbidden on all profile routes.
2. **Role-Based Permissions**: Profiles distinguish between `elderly` (owner), `family`, and `caretaker` with granular read-only vs. full-access permissions.
3. **Unambiguous Passcodes**: Invite codes use an 8-character uppercase alphabet excluding visually confusing characters (`0`, `O`, `1`, `I`), making them easy to communicate verbally or by phone.
4. **Single-Use Passcodes**: Invite codes automatically deactivate upon redemption to prevent replay attacks.
5. **Deduplication Safeguards**: Doses and reminder emails utilize unique compound keys (`profile_id`, `medication_id`, `date`, `time`) to prevent duplicate medication administration and spam.
6. **Prescribing Disclaimer**: All emergency health endpoints provide transparent disclaimers that information is informational and does not constitute medical prescribing.

---

## Getting Started

### Prerequisites
- Python 3.10, 3.11, 3.12, 3.13, or 3.14
- Git

### 1. Clone & Set Up Virtual Environment
```bash
git clone https://github.com/Dibyendu-maker/eldercare_connect.git
cd eldercare_connect

python -m venv venv
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On macOS / Linux:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy the template configuration file:
```bash
cp .env.example .env
```
Key configuration parameters in `.env`:
| Parameter | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | Environment mode (`development`, `test`, `production`) |
| `DATABASE_URL` | `sqlite:///./eldercare_connect.db` | SQLAlchemy connection string |
| `SECRET_KEY` | *(dev fallback)* | High-entropy signing key (required in production) |
| `ALLOWED_ORIGINS` | `http://localhost:3000,...` | Comma-separated allowed CORS origins |
| `RESEND_API_KEY` | *None* | Resend API key (optional; transparent mock mode if unset) |
| `EMAIL_FROM` | `notifications@...` | Sender email address for reminders |

### 4. Run the Development Server
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
Interactive API documentation will be available at:
- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## Testing

The test suite validates authentication, role-based authorization, multi-tenant isolation, medication CRUD, dose deduplication, appointments, and notification dispatch:

```bash
# Run complete test suite with short tracebacks
pytest tests -v --tb=short

# Run specific test suite
pytest tests/test_auth.py -v
pytest tests/test_appointments.py -v
pytest tests/test_medications.py -v
pytest tests/test_roles_access.py -v
pytest tests/test_health_and_dashboard.py -v
pytest tests/test_notifications.py -v
```

All 18 tests run in an isolated in-memory SQLite database (`StaticPool`) and complete in ~2 seconds.

---

## API Overview

| Route | Method | Description |
|---|---|---|
| `/health` | `GET` | System and database connectivity check |
| `/api/auth/register` | `POST` | Register user (elderly, family, caretaker) |
| `/api/auth/login` | `POST` | Authenticate and obtain JWT token |
| `/api/auth/me` | `GET` | Current user profile |
| `/api/profiles` | `GET` / `POST` | List accessible profiles or create new care profile |
| `/api/profiles/{id}/dashboard` | `GET` | Daily medication summary, today's doses, appointments |
| `/api/profiles/{id}/medications` | `GET` / `POST` | List or register medication schedules |
| `/api/profiles/{id}/medications/{mid}/doses` | `POST` | Log taken / skipped / missed dose (with deduplication) |
| `/api/profiles/{id}/appointments` | `GET` / `POST` | List or schedule healthcare appointments |
| `/api/profiles/{id}/appointments/{aid}/send-reminder` | `POST` | Dispatch appointment reminder |
| `/api/profiles/{id}/invites` | `POST` | Generate secure, expiring care-circle passcode |
| `/api/profiles/join` | `POST` | Join care circle with invite passcode |
| `/api/profiles/{id}/circle/members` | `GET` | List care circle members |
| `/api/profiles/{id}/circle/members/{mid}` | `DELETE` | Revoke care circle member access |
| `/api/profiles/{id}/health` | `GET` / `PUT` | Emergency health card (blood type, allergies, contacts) |
| `/api/notifications/status` | `GET` | Live Resend configuration and provider status |
| `/api/notifications/trigger-check/{id}` | `POST` | Automated check for overdue doses and upcoming events |

---

## License

MIT License. Designed and developed for elderly care coordination.
