# ==========================================
# Application configuration constants
# Change values here to adjust app behavior
# ==========================================

# Maximum allowed distance (in meters) between the instructor's
# location when starting a session and a student's location when
# submitting attendance. Submissions beyond this are rejected.
MAX_ATTENDANCE_DISTANCE_METERS = 30

# Global switch: when True, students cannot log in while ANY lecture
# session is active anywhere in the system. Only safe to enable when
# a single instructor is using the app at a time. Default: off.
ENABLE_GLOBAL_LOGIN_LOCK = False