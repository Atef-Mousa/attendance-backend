import asyncio
import os
import time

import requests
from sqlalchemy import select

import models
from database import AsyncSessionLocal

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")


async def ensure_course_exists(instructor_email: str, code: str = "CS101", title: str = "Intro to CS") -> None:
    """
    The app does not expose a course-creation endpoint in this project, so we seed the
    required course row directly in the database before starting an OTP session.
    """
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(models.Course).where(models.Course.code == code))
        if existing.scalar_one_or_none():
            return

        instructor_result = await session.execute(select(models.User).where(models.User.email == instructor_email))
        instructor = instructor_result.scalar_one_or_none()
        if instructor is None:
            raise RuntimeError(f"Instructor not found for email: {instructor_email}")

        session.add(models.Course(code=code, title=title, instructor_id=instructor.id))
        await session.commit()


def register_user(email: str, password: str, full_name: str, role: str):
    response = requests.post(
        f"{BASE_URL}/api/v1/register",
        json={
            "email": email,
            "password": password,
            "full_name": full_name,
            "role": role,
        },
        timeout=10,
    )
    print(f"[register] {role}: {response.status_code} -> {response.text}")
    response.raise_for_status()
    return response.json()


def login_user(email: str, password: str):
    response = requests.post(
        f"{BASE_URL}/api/v1/login",
        data={"username": email, "password": password},
        timeout=10,
    )
    print(f"[login] {email}: {response.status_code} -> {response.text}")
    response.raise_for_status()
    return response.json()["access_token"]


def create_course(token: str, code: str, title: str):
    response = requests.post(
        f"{BASE_URL}/api/v1/courses",
        headers={"Authorization": f"Bearer {token}"},
        json={"code": code, "title": title},
        timeout=10,
    )
    print(f"[create_course]: {response.status_code} -> {response.text}")
    response.raise_for_status()
    return response.json()


def start_session(token: str, course_id: int, ttl_seconds: int = 60):
    response = requests.post(
        f"{BASE_URL}/api/v1/sessions/start",
        headers={"Authorization": f"Bearer {token}"},
        json={"course_id": course_id, "ttl_seconds": ttl_seconds},
        timeout=10,
    )
    print(f"[start_session]: {response.status_code} -> {response.text}")
    response.raise_for_status()
    return response.json()


def submit_attendance(token: str, otp_code: str):
    response = requests.post(
        f"{BASE_URL}/api/v1/attendance/submit",
        headers={"Authorization": f"Bearer {token}"},
        json={"otp_code": otp_code},
        timeout=10,
    )
    print(f"[submit_attendance]: {response.status_code} -> {response.text}")
    return response


def main():
    ts = int(time.time())
    instructor_email = f"admin_{ts}@school.edu"
    student_email = f"student_{ts}@school.edu"

    print("=== Frontend-like OTP attendance simulation ===")

    register_user(instructor_email, "adminpass123", "Mr. Admin", "instructor")
    register_user(student_email, "studentpass123", "Jane Student", "student")

    asyncio.run(ensure_course_exists(instructor_email))

    instructor_token = login_user(instructor_email, "adminpass123")
    student_token = login_user(student_email, "studentpass123")

    course = create_course(instructor_token, code=f"CS101_{ts}", title="Intro to CS")
    course_id = course["id"]

    session = start_session(instructor_token, course_id=course_id)
    otp_code = session["otp_code"]
    print(f"Generated OTP for student attendance: {otp_code}")

    first_submit = submit_attendance(student_token, otp_code)
    print("First attendance submission result:", first_submit.status_code)

    second_submit = submit_attendance(student_token, otp_code)
    print("Duplicate attendance submission result:", second_submit.status_code)
    if second_submit.status_code == 409:
        print("Duplicate attendance blocked successfully.")


if __name__ == "__main__":
    main()
