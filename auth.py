import os
from datetime import datetime, timezone

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE = "tc_session"
REMEMBER_SECONDS = 14 * 24 * 3600
SHORT_SECONDS = 12 * 3600
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"

_serializer = URLSafeTimedSerializer(os.environ["SESSION_SECRET"], salt="tc-session")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


DUMMY_HASH = hash_password("not-a-real-account-password")


def make_session_token(user_id: int, remember: bool) -> str:
    return _serializer.dumps({"uid": user_id, "r": bool(remember)})


def read_session_token(token: str):
    try:
        data, issued_at = _serializer.loads(token, max_age=REMEMBER_SECONDS, return_timestamp=True)
    except (BadSignature, SignatureExpired):
        return None
    if not data.get("r"):
        age = (datetime.now(timezone.utc) - issued_at).total_seconds()
        if age > SHORT_SECONDS:
            return None
    return data.get("uid")


def safe_next(target: str) -> str:
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return "/"