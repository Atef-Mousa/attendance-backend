import random
import string
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import models

def generate_numeric_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))

class AttendanceService:

    @staticmethod
    async def create_lecture_session(db: AsyncSession, course_id: int, ttl_seconds: int) -> models.LectureSession:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)
        otp = generate_numeric_otp(6)

        # Deactivate any lingering active sessions for this course using async update()
        await db.execute(
            update(models.LectureSession)
            .where(
                models.LectureSession.course_id == course_id,
                models.LectureSession.is_active == True
            )
            .values(is_active=False)
        )

        session = models.LectureSession(
            course_id=course_id,
            otp_code=otp,
            created_at=now,
            expires_at=expires_at,
            is_active=True
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    @staticmethod
    async def submit_attendance(db: AsyncSession, student_id: int, otp_code: str) -> models.AttendanceRecord:
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

        # 3. Check for Duplicate Attendance Entry
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

        # 4. Record Attendance
        record = models.AttendanceRecord(
            session_id=session.id,
            student_id=student_id,
            timestamp=now
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record