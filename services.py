import random
import string
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from config import MAX_ATTENDANCE_DISTANCE_METERS
import models

def generate_numeric_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))

class AttendanceService:

    @staticmethod
    async def create_lecture_session(
        db: AsyncSession,
        course_id: int,
        ttl_seconds: int,
        latitude: float,
        longitude: float,
    ) -> models.LectureSession:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)
        otp = generate_numeric_otp(6)

        await db.execute(
            update(models.LectureSession)
            .where(
                models.LectureSession.course_id == course_id,
                models.LectureSession.is_active == True
            )
            .values(is_active=False, task_submissions_open=False)
        )

        session = models.LectureSession(
            course_id=course_id,
            otp_code=otp,
            created_at=now,
            expires_at=expires_at,
            is_active=True,
            latitude=latitude,
            longitude=longitude,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    @staticmethod
    async def submit_attendance(
        db: AsyncSession, student_id: int, otp_code: str, token_iat: Optional[datetime] = None
    ) -> models.AttendanceRecord:
        now = datetime.now(timezone.utc)

        # 1. Fetch active session matching OTP
        result = await db.execute(
            select(models.LectureSession).where(
                models.LectureSession.otp_code == otp_code,
                models.LectureSession.is_active == True
            )
        )
        session = result.scalar_one_or_none()

        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or inactive OTP")

        # 2. Check Expiration
        if session.expires_at < now:
            session.is_active = False
            await db.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired")

        # 3. Reject if the student logged in after this session already started
        # (unknown iat from older tokens is allowed through, not rejected)
        if token_iat is not None and token_iat > session.created_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You logged in after this session started; please contact your instructor if this is a mistake"
            )

        # 4. Check for Duplicate Attendance Entry
        dup_result = await db.execute(
            select(models.AttendanceRecord).where(
                models.AttendanceRecord.session_id == session.id,
                models.AttendanceRecord.student_id == student_id
            )
        )
        if dup_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail="Attendance already recorded for this session"
            )

        # 5. Record Attendance
        record = models.AttendanceRecord(
            session_id=session.id,
            student_id=student_id,
            timestamp=now
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record

    @staticmethod
    async def submit_task(
        db: AsyncSession, student_id: int, session_id: int, submission_link: str
    ) -> models.TaskSubmission:
        # 1. The session ID must refer to a real session
        session_result = await db.execute(
            select(models.LectureSession).where(models.LectureSession.id == session_id)
        )
        session = session_result.scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid session ID")

        # 2. Task submissions must still be open for this session
        if not session.task_submissions_open:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This session has expired, task submissions are no longer accepted"
            )

        # 3. Check for Duplicate Submission
        dup_result = await db.execute(
            select(models.TaskSubmission).where(
                models.TaskSubmission.session_id == session_id,
                models.TaskSubmission.student_id == student_id
            )
        )
        if dup_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task already submitted for this session"
            )

        # 4. Record Submission
        submission = models.TaskSubmission(
            session_id=session_id,
            student_id=student_id,
            submission_link=submission_link,
        )
        db.add(submission)
        await db.commit()
        await db.refresh(submission)
        return submission

    @staticmethod
    async def search_students(db: AsyncSession, query: str) -> list[models.User]:
        result = await db.execute(
            select(models.User).where(
                models.User.role == models.Role.STUDENT,
                models.User.full_name.ilike(f"%{query}%"),
            )
        )
        return result.scalars().all()

    @staticmethod
    async def get_student_performance(db: AsyncSession, student_id: int, instructor_id: int):
        # 1. The target must be a real student
        student_result = await db.execute(
            select(models.User).where(
                models.User.id == student_id,
                models.User.role == models.Role.STUDENT,
            )
        )
        student = student_result.scalar_one_or_none()
        if student is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

        # 2. Only the instructor's own courses count toward the analysis
        courses_result = await db.execute(
            select(models.Course).where(models.Course.instructor_id == instructor_id)
        )
        courses = courses_result.scalars().all()
        course_ids = [course.id for course in courses]

        sessions_by_course: dict[int, int] = {}
        attended_by_course: dict[int, int] = {}
        submissions = []

        if course_ids:
            sessions_result = await db.execute(
                select(models.LectureSession.course_id, func.count(models.LectureSession.id))
                .where(models.LectureSession.course_id.in_(course_ids))
                .group_by(models.LectureSession.course_id)
            )
            sessions_by_course = dict(sessions_result.all())

            attended_result = await db.execute(
                select(models.LectureSession.course_id, func.count(models.AttendanceRecord.id))
                .join(models.AttendanceRecord, models.AttendanceRecord.session_id == models.LectureSession.id)
                .where(
                    models.LectureSession.course_id.in_(course_ids),
                    models.AttendanceRecord.student_id == student_id,
                )
                .group_by(models.LectureSession.course_id)
            )
            attended_by_course = dict(attended_result.all())

            submissions_result = await db.execute(
                select(models.TaskSubmission)
                .join(models.LectureSession, models.LectureSession.id == models.TaskSubmission.session_id)
                .where(
                    models.TaskSubmission.student_id == student_id,
                    models.LectureSession.course_id.in_(course_ids),
                )
            )
            submissions = submissions_result.scalars().all()

        courses_performance = [
            {
                "course_id": course.id,
                "code": course.code,
                "title": course.title,
                "sessions_held": sessions_by_course.get(course.id, 0),
                "attended_count": attended_by_course.get(course.id, 0),
            }
            for course in courses
        ]

        return student, courses_performance, submissions

    @staticmethod
    async def set_task_grade(
        db: AsyncSession, submission_id: int, instructor_id: int, grade: float
    ) -> models.TaskSubmission:
        result = await db.execute(
            select(models.TaskSubmission)
            .join(models.LectureSession, models.LectureSession.id == models.TaskSubmission.session_id)
            .join(models.Course, models.Course.id == models.LectureSession.course_id)
            .where(
                models.TaskSubmission.id == submission_id,
                models.Course.instructor_id == instructor_id,
            )
        )
        submission = result.scalar_one_or_none()
        if submission is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task submission not found")

        submission.grade = grade
        await db.commit()
        await db.refresh(submission)
        return submission