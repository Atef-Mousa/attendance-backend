# Attendance System — Backend (FastAPI)

An async FastAPI backend for an OTP-based attendance system. Instructors
start a timed lecture session which generates a 6-digit OTP; students
submit that OTP to mark themselves present.

## Tech Stack
- **Framework:** FastAPI (async)
- **ORM:** SQLAlchemy 2.0 (async)
- **Database:** PostgreSQL (hosted on [Neon](https://neon.tech))
- **Driver:** asyncpg
- **Auth:** JWT (PyJWT), password hashing with bcrypt
- **Deployment:** [Render](https://render.com)

## Live Deployment
- API base URL: `https://attendance-backend-6zpt.onrender.com`
- Interactive API docs (Swagger UI): `https://attendance-backend-6zpt.onrender.com/docs`

Note: the free Render tier spins down after inactivity — the first
request after idle time can take 30-50 seconds to respond.

## Project Structure
```
main.py        API routes (auth, courses, sessions, attendance, settings)
models.py      SQLAlchemy models (User, Course, LectureSession, AttendanceRecord)
schemas.py     Pydantic request/response schemas
services.py    Business logic (OTP generation, attendance submission)
auth.py        JWT creation/validation, password hashing, role-based access
database.py    Async engine, session factory, DB dependency
test/          Pytest test suite (uses httpx AsyncClient against the ASGI app)
```

## Environment Variables
Create a `.env` file in the project root (never commit this file):

```
DATABASE_URL=postgresql+asyncpg://user:password@host/dbname?ssl=require
SECRET_KEY=a-long-random-secret-key
```

Generate a strong `SECRET_KEY` with:
```
python -c "import secrets; print(secrets.token_hex(32))"
```

If your database is behind a connection pooler (e.g. Neon's pooled
endpoint), the engine is configured with `statement_cache_size: 0` in
`database.py` to avoid prepared-statement conflicts with PgBouncer.

## Running Locally
```bash
pip install -r requirements.txt
python main.py
```
The server starts at `http://127.0.0.1:8000`. Tables are created
automatically on startup if they don't exist.

## Running Tests
```bash
pytest test/test_api.py
```

## Key Endpoints
| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/api/v1/register` | Register a new user | None |
| POST | `/api/v1/login` | Log in, returns JWT | None |
| GET | `/api/v1/me` | Get current user info | Any role |
| GET / POST | `/api/v1/courses` | List / create courses | Instructor |
| POST | `/api/v1/sessions/start` | Start a timed OTP session for a course | Instructor |
| POST | `/api/v1/sessions/{id}/stop` | Manually stop a session early | Instructor |
| GET | `/api/v1/courses/{id}/active_session` | Get the current/last session for a course | Instructor |
| GET | `/api/v1/sessions/{id}/attendance` | List students who attended a session | Instructor |
| POST | `/api/v1/attendance/submit` | Submit an OTP to mark attendance | Student |
| GET | `/api/v1/settings/lock_status` | Check if login/logout is currently locked | None |

## Design Notes / Known Limitations
- Only one active session is allowed per course at a time — starting a
  new session automatically deactivates any previous one for that course.
- While any lecture session is active, student login and logout are
  blocked system-wide (an anti-sharing measure to stop one logged-in
  device being passed between students). This lock is currently global
  rather than scoped per-course, since the app has no course-enrollment
  model yet.
- Sessions expire based on `ttl_seconds` set at creation; expiry is
  checked on read (lazily), not via a background job.

## Related Repo
Frontend (Flutter Web): see the companion `attendance-frontend` repository.
