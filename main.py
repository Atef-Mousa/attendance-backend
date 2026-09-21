from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import models, schemas, auth
from database import engine, get_db
from services import AttendanceService
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Non-blocking async table initialization on startup
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    yield


app = FastAPI(title="OTP Student Attendance API (Async)", version="1.0.0", lifespan=lifespan)



# Add CORS Middleware to allow requests from Flutter Web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows requests from any origin (Flutter Web)
    allow_credentials=True,
    allow_methods=["*"],  # Allows POST, GET, OPTIONS, etc.
    allow_headers=["*"],  # Allows headers like Content-Type, Authorization
)
# --- AUTHENTICATION ENDPOINTS ---

@app.post("/api/v1/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    name_result = await db.execute(select(models.User).where(models.User.full_name == user_in.full_name))
    if name_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Full name already taken, please use a unique name")

    user = models.User(
        email=user_in.email,
        hashed_password=auth.get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

# @app.post("/api/v1/login", response_model=schemas.Token)
# async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
#     result = await db.execute(select(models.User).where(models.User.email == form_data.username))
#     user = result.scalar_one_or_none()
    
#     if not user or not auth.verify_password(form_data.password, user.hashed_password):
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
#     access_token = auth.create_access_token(data={"sub": str(user.id), "role": user.role.value})
#     return {"access_token": access_token, "token_type": "bearer"}


@app.post("/api/v1/login", response_model=schemas.Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.full_name == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Block student logins while any lecture session is active
    if user.role == models.Role.STUDENT:
        now = datetime.now(timezone.utc)
        active_session_result = await db.execute(
            select(models.LectureSession).where(
                models.LectureSession.is_active == True,
                models.LectureSession.expires_at > now,
            )
        )
        if active_session_result.scalars().first() is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Login is currently locked while a session is active."
            )

    access_token = auth.create_access_token(data={"sub": str(user.id), "role": user.role.value})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/v1/me", response_model=schemas.UserResponse)
async def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

# --- COURSE ENDPOINTS ---

@app.get("/api/v1/courses", response_model=list[schemas.CourseResponse])
async def get_courses(
    db: AsyncSession = Depends(get_db),
    instructor: models.User = Depends(auth.require_role(models.Role.INSTRUCTOR)),
):
    result = await db.execute(
        select(models.Course).where(models.Course.instructor_id == instructor.id)
    )
    return result.scalars().all()


@app.post("/api/v1/courses", response_model=schemas.CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(
    course_in: schemas.CourseCreate,
    db: AsyncSession = Depends(get_db),
    instructor: models.User = Depends(auth.require_role(models.Role.INSTRUCTOR)),
):
    existing = await db.execute(select(models.Course).where(models.Course.code == course_in.code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Course code already exists")

    course = models.Course(
        code=course_in.code,
        title=course_in.title,
        instructor_id=instructor.id,
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course

# --- ATTENDANCE & SESSION ENDPOINTS ---

@app.post("/api/v1/sessions/start", response_model=schemas.SessionResponse)
async def start_session(
    session_in: schemas.SessionCreate,
    db: AsyncSession = Depends(get_db),
    instructor: models.User = Depends(auth.require_role(models.Role.INSTRUCTOR))
):
    return await AttendanceService.create_lecture_session(
        db=db,
        course_id=session_in.course_id,
        ttl_seconds=session_in.ttl_seconds,
        latitude=session_in.latitude,
        longitude=session_in.longitude,
    )
@app.post("/api/v1/attendance/submit", response_model=schemas.AttendanceResponse)
async def submit_attendance(
    payload: schemas.AttendanceSubmit,
    db: AsyncSession = Depends(get_db),
    student: models.User = Depends(auth.require_role(models.Role.STUDENT))
):
    record = await AttendanceService.submit_attendance(
        db=db, 
        student_id=student.id, 
        otp_code=payload.otp_code
    )
    return {
        "id": record.id,
        "session_id": record.session_id,
        "student_id": record.student_id,
        "timestamp": record.timestamp,
        "message": "Attendance successfully recorded"
    }


@app.get("/api/v1/sessions/{session_id}/attendance", response_model=list[schemas.AttendanceRecordResponse])
async def get_session_attendance(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    instructor: models.User = Depends(auth.require_role(models.Role.INSTRUCTOR)),
):
    session_result = await db.execute(
        select(models.LectureSession)
        .join(models.Course, models.Course.id == models.LectureSession.course_id)
        .where(
            models.LectureSession.id == session_id,
            models.Course.instructor_id == instructor.id,
        )
    )
    if session_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(models.AttendanceRecord, models.User)
        .join(models.User, models.User.id == models.AttendanceRecord.student_id)
        .where(models.AttendanceRecord.session_id == session_id)
    )
    return [
        {
            "id": record.id,
            "session_id": record.session_id,
            "student_id": record.student_id,
            "student_name": student.full_name,
            "timestamp": record.timestamp,
        }
        for record, student in result.all()
    ]


@app.get("/api/v1/settings/lock_status", response_model=schemas.LockStatusResponse)
async def get_lock_status(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(models.LectureSession).where(
            models.LectureSession.is_active == True,
            models.LectureSession.expires_at > now,
        )
    )
    active_session = result.scalars().first()
    return {"login_locked": active_session is not None}


@app.post("/api/v1/sessions/{session_id}/stop", response_model=schemas.SessionResponse)
async def stop_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    instructor: models.User = Depends(auth.require_role(models.Role.INSTRUCTOR)),
):
    result = await db.execute(
        select(models.LectureSession)
        .join(models.Course, models.Course.id == models.LectureSession.course_id)
        .where(
            models.LectureSession.id == session_id,
            models.Course.instructor_id == instructor.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    session.is_active = False
    await db.commit()
    await db.refresh(session)
    return session


@app.post("/api/v1/sessions/{session_id}/close_task_submissions", response_model=schemas.SessionResponse)
async def close_task_submissions(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    instructor: models.User = Depends(auth.require_role(models.Role.INSTRUCTOR)),
):
    result = await db.execute(
        select(models.LectureSession)
        .join(models.Course, models.Course.id == models.LectureSession.course_id)
        .where(
            models.LectureSession.id == session_id,
            models.Course.instructor_id == instructor.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    session.task_submissions_open = False
    await db.commit()
    await db.refresh(session)
    return session


# --- TASK SUBMISSION ENDPOINTS ---

@app.post(
    "/api/v1/sessions/{session_id}/submit_task",
    response_model=schemas.TaskSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_task(
    session_id: int,
    payload: schemas.TaskSubmissionCreate,
    db: AsyncSession = Depends(get_db),
    student: models.User = Depends(auth.require_role(models.Role.STUDENT))
):
    submission = await AttendanceService.submit_task(
        db=db,
        student_id=student.id,
        session_id=session_id,
        submission_link=str(payload.submission_link),
    )
    return {
        "id": submission.id,
        "session_id": submission.session_id,
        "student_id": submission.student_id,
        "student_name": student.full_name,
        "submission_link": submission.submission_link,
        "submitted_at": submission.submitted_at,
    }


@app.get("/api/v1/sessions/{session_id}/task_submissions", response_model=list[schemas.TaskSubmissionResponse])
async def get_task_submissions(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    instructor: models.User = Depends(auth.require_role(models.Role.INSTRUCTOR)),
):
    session_result = await db.execute(
        select(models.LectureSession)
        .join(models.Course, models.Course.id == models.LectureSession.course_id)
        .where(
            models.LectureSession.id == session_id,
            models.Course.instructor_id == instructor.id,
        )
    )
    if session_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(models.TaskSubmission, models.User)
        .join(models.User, models.User.id == models.TaskSubmission.student_id)
        .where(models.TaskSubmission.session_id == session_id)
    )
    return [
        {
            "id": submission.id,
            "session_id": submission.session_id,
            "student_id": submission.student_id,
            "student_name": student.full_name,
            "submission_link": submission.submission_link,
            "submitted_at": submission.submitted_at,
        }
        for submission, student in result.all()
    ]


# --- STUDENT PERFORMANCE ENDPOINTS ---

@app.get("/api/v1/students/search", response_model=list[schemas.StudentSearchResult])
async def search_students(
    q: str = Query(min_length=1),
    db: AsyncSession = Depends(get_db),
    instructor: models.User = Depends(auth.require_role(models.Role.INSTRUCTOR)),
):
    return await AttendanceService.search_students(db=db, query=q)


@app.get("/api/v1/students/{student_id}/performance", response_model=schemas.StudentPerformanceResponse)
async def get_student_performance(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    instructor: models.User = Depends(auth.require_role(models.Role.INSTRUCTOR)),
):
    student, courses_performance, submissions = await AttendanceService.get_student_performance(
        db=db, student_id=student_id, instructor_id=instructor.id
    )
    return {
        "student_id": student.id,
        "full_name": student.full_name,
        "email": student.email,
        "courses": courses_performance,
        "task_submissions": [
            {
                "id": submission.id,
                "session_id": submission.session_id,
                "student_id": submission.student_id,
                "student_name": student.full_name,
                "submission_link": submission.submission_link,
                "submitted_at": submission.submitted_at,
                "grade": submission.grade,
            }
            for submission in submissions
        ],
    }


@app.patch("/api/v1/task_submissions/{submission_id}/grade", response_model=schemas.TaskSubmissionResponse)
async def set_task_grade(
    submission_id: int,
    payload: schemas.GradeUpdate,
    db: AsyncSession = Depends(get_db),
    instructor: models.User = Depends(auth.require_role(models.Role.INSTRUCTOR)),
):
    submission = await AttendanceService.set_task_grade(
        db=db, submission_id=submission_id, instructor_id=instructor.id, grade=payload.grade
    )
    student_result = await db.execute(select(models.User).where(models.User.id == submission.student_id))
    student = student_result.scalar_one()
    return {
        "id": submission.id,
        "session_id": submission.session_id,
        "student_id": submission.student_id,
        "student_name": student.full_name,
        "submission_link": submission.submission_link,
        "submitted_at": submission.submitted_at,
        "grade": submission.grade,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)