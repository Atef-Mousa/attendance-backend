import time
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from main import app
import models
from database import AsyncSessionLocal

BASE_URL = "http://testserver"

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.mark.anyio
async def test_create_course_for_instructor():
    ts = int(time.time())
    inst_email = f"instructor_course_{ts}@university.edu"
    course_code = f"CS102_{ts}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as ac:
        register_resp = await ac.post(
            "/api/v1/register",
            json={
                "email": inst_email,
                "password": "securepassword123",
                "full_name": "Dr. Course Creator",
                "role": "instructor",
            },
        )
        assert register_resp.status_code == 201

        login_resp = await ac.post(
            "/api/v1/login",
            data={"username": inst_email, "password": "securepassword123"},
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        course_resp = await ac.post(
            "/api/v1/courses",
            headers={"Authorization": f"Bearer {token}"},
            json={"code": course_code, "title": "Advanced Algorithms"},
        )
        assert course_resp.status_code == 201
        body = course_resp.json()
        assert body["code"] == course_code
        assert body["title"] == "Advanced Algorithms"
        assert body["instructor_id"] >= 1


@pytest.mark.anyio
async def test_instructor_can_list_courses():
    ts = int(time.time())
    inst_email = f"instructor_list_{ts}@university.edu"
    course_code = f"CS_LIST_{ts}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as ac:
        reg = await ac.post(
            "/api/v1/register",
            json={
                "email": inst_email,
                "password": "securepassword123",
                "full_name": "Dr. List Courses",
                "role": "instructor",
            },
        )
        assert reg.status_code == 201

        login = await ac.post(
            "/api/v1/login",
            data={"username": inst_email, "password": "securepassword123"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        create = await ac.post(
            "/api/v1/courses",
            headers={"Authorization": f"Bearer {token}"},
            json={"code": course_code, "title": "Course Listing Test"},
        )
        assert create.status_code == 201

        list_resp = await ac.get(
            "/api/v1/courses",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        courses = list_resp.json()
        assert any(item["code"] == course_code for item in courses)


@pytest.mark.anyio
async def test_full_attendance_workflow():
    ts = int(time.time())
    inst_email = f"instructor_{ts}@university.edu"
    stud_email = f"student_{ts}@university.edu"
    course_code = f"CS101_{ts}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as ac:
        
        # 1. Register Instructor
        instructor_resp = await ac.post("/api/v1/register", json={
            "email": inst_email,
            "password": "securepassword123",
            "full_name": "Dr. Smith",
            "role": "instructor"
        })
        assert instructor_resp.status_code == 201
        
        # 2. Register Student
        student_resp = await ac.post("/api/v1/register", json={
            "email": stud_email,
            "password": "studentpassword123",
            "full_name": "John Doe",
            "role": "student"
        })
        assert student_resp.status_code == 201

        # 3. Login Instructor & Get Token
        inst_login = await ac.post("/api/v1/login", data={
            "username": inst_email,
            "password": "securepassword123"
        })
        assert inst_login.status_code == 200
        inst_token = inst_login.json()["access_token"]

        # 4. Create a course via the instructor API
        course_resp = await ac.post(
            "/api/v1/courses",
            headers={"Authorization": f"Bearer {inst_token}"},
            json={"code": course_code, "title": "Intro to CS"},
        )
        assert course_resp.status_code == 201
        course_id = course_resp.json()["id"]

        # 5. Login Student & Get Token
        stud_login = await ac.post("/api/v1/login", data={
            "username": stud_email,
            "password": "studentpassword123"
        })
        assert stud_login.status_code == 200
        stud_token = stud_login.json()["access_token"]

        # 6. Instructor Creates Session (OTP Generation)
        session_resp = await ac.post(
            "/api/v1/sessions/start",
            headers={"Authorization": f"Bearer {inst_token}"},
            json={"course_id": course_id, "ttl_seconds": 60}
        )
        assert session_resp.status_code == 200
        otp_code = session_resp.json()["otp_code"]
        assert len(otp_code) == 6

        # 7. Student Submits Valid OTP
        attendance_resp = await ac.post(
            "/api/v1/attendance/submit",
            headers={"Authorization": f"Bearer {stud_token}"},
            json={"otp_code": otp_code}
        )
        assert attendance_resp.status_code == 200

        # 8. Duplicate Submission Guard (Should return 409)
        duplicate_resp = await ac.post(
            "/api/v1/attendance/submit",
            headers={"Authorization": f"Bearer {stud_token}"},
            json={"otp_code": otp_code}
        )
        assert duplicate_resp.status_code == 409