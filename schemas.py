from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict, HttpUrl
from models import Role

# User Schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=3, max_length=255)
    role: Role = Role.STUDENT

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: Role

    model_config = ConfigDict(from_attributes=True)

# Auth Schemas
class Token(BaseModel):
    access_token: str
    token_type: str

# Session & OTP Schemas
class CourseCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    title: str = Field(min_length=2, max_length=255)

class CourseResponse(BaseModel):
    id: int
    code: str
    title: str
    instructor_id: int

    model_config = ConfigDict(from_attributes=True)

class SessionCreate(BaseModel):
    course_id: int
    ttl_seconds: int = Field(default=60, ge=30, le=300)
    latitude: float
    longitude: float

class SessionResponse(BaseModel):
    id: int
    course_id: int
    otp_code: str
    expires_at: datetime
    is_active: bool
    latitude: float
    longitude: float
    task_submissions_open: bool

    model_config = ConfigDict(from_attributes=True)

class AttendanceSubmit(BaseModel):
    otp_code: str = Field(min_length=6, max_length=6)
    latitude: float
    longitude: float

class AttendanceResponse(BaseModel):
    id: int
    session_id: int
    student_id: int
    timestamp: datetime
    message: str = "Attendance registered successfully"

    model_config = ConfigDict(from_attributes=True)


class LockStatusResponse(BaseModel):
    login_locked: bool

    model_config = ConfigDict(from_attributes=True)

class AttendanceRecordResponse(BaseModel):
    id: int
    session_id: int
    student_id: int
    student_name: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

# Task Submission Schemas
class TaskSubmissionCreate(BaseModel):
    submission_link: HttpUrl

class TaskSubmissionResponse(BaseModel):
    id: int
    session_id: int
    student_id: int
    student_name: str
    submission_link: str
    submitted_at: datetime

    model_config = ConfigDict(from_attributes=True)

