import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.core.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    AUTH_SECRET_KEY,
    BUILTIN_EMAIL,
    BUILTIN_PASSWORD,
    BUILTIN_USERNAME,
)
from app.core.database import User, get_db
from app.shared.cache import USER_CACHE_TTL_SECONDS, get_json, set_json, stable_hash


security = HTTPBearer(auto_error=False)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), 120_000)
    return f"pbkdf2_sha256$120000${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, iterations, salt, expected = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        int(iterations),
    ).hex()
    return hmac.compare_digest(digest, expected)


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.user_id,
        "email": user.email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(AUTH_SECRET_KEY.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64encode(signature)}"


def decode_access_token(token: str) -> dict:
    try:
        body, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的登录凭证") from exc

    expected = hmac.new(AUTH_SECRET_KEY.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64encode(expected), signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的登录凭证")

    try:
        payload = json.loads(_b64decode(body))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的登录凭证") from exc

    if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期")
    return payload


def user_to_dict(user: User) -> dict:
    return {
        "user_id": user.user_id,
        "username": user.username or "",
        "email": user.email or "",
    }


def register_user(username: str, email: str, password: str) -> dict:
    now = datetime.now(timezone.utc)
    normalized_email = _normalize_email(email)
    normalized_username = username.strip()
    with get_db() as db:
        existing = db.execute(
            select(User).where(
                (User.email == normalized_email) | (User.username == normalized_username)
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱或用户名已注册")

        user = User(
            user_id=uuid.uuid4().hex,
            username=normalized_username,
            email=normalized_email,
            password_hash=hash_password(password),
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    from app.shared import db_log
    db_log.log_event(
        entity_type="user",
        entity_id=user.user_id,
        event_type="user.registered",
        user_id=user.user_id,
        meta={"username": normalized_username},
    )
    return {"access_token": create_access_token(user), "user": user_to_dict(user)}


def login_user(account: str, password: str) -> dict:
    normalized_account = account.strip().lower()
    with get_db() as db:
        user = db.execute(
            select(User).where(
                (User.email == normalized_account) | (User.username == account.strip())
            )
        ).scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")

    return {"access_token": create_access_token(user), "user": user_to_dict(user)}


def ensure_builtin_user() -> None:
    now = datetime.now(timezone.utc)
    username = BUILTIN_USERNAME.strip()
    email = _normalize_email(BUILTIN_EMAIL)
    if not username or not BUILTIN_PASSWORD:
        return

    with get_db() as db:
        user = db.execute(
            select(User).where((User.username == username) | (User.email == email))
        ).scalar_one_or_none()
        if user is None:
            db.add(
                User(
                    user_id=uuid.uuid4().hex,
                    username=username,
                    email=email,
                    password_hash=hash_password(BUILTIN_PASSWORD),
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            user.username = username
            user.email = email
            user.password_hash = hash_password(BUILTIN_PASSWORD)
            user.updated_at = now
        db.commit()


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的登录凭证")

    cache_key = f"cache:user_auth:{stable_hash(token)}"
    cached = get_json(cache_key)
    if cached is not None and cached.get("user_id") == user_id:
        return User(
            user_id=cached["user_id"],
            username=cached.get("username"),
            email=cached.get("email"),
            password_hash=cached.get("password_hash"),
            created_at=None,
            updated_at=None,
        )

    with get_db() as db:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
        cached_user = {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "password_hash": user.password_hash,
        }
        set_json(cache_key, cached_user, USER_CACHE_TTL_SECONDS)
        return user
