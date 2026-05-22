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
    REFRESH_TOKEN_EXPIRE_DAYS,
    REQUIRE_EMAIL_VERIFICATION,
)
from app.core.database import User, get_db
from app.shared.cache import (
    EMAIL_TOKEN_TTL_SECONDS,
    REFRESH_TOKEN_TTL_SECONDS,
    RESET_TOKEN_TTL_SECONDS,
    USER_CACHE_TTL_SECONDS,
    delete_pattern,
    get_json,
    get_redis,
    get_text,
    set_json,
    set_text,
    stable_hash,
)

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
        "email_verified": bool(user.email_verified),
    }


# ── Refresh Token ──────────────────────────────────────────────────────────────

def create_refresh_token(user: User) -> str:
    token = secrets.token_urlsafe(32)
    key = f"auth:refresh:{stable_hash(token)}"
    set_text(key, json.dumps({"user_id": user.user_id, "issued_at": int(datetime.now(timezone.utc).timestamp())}), REFRESH_TOKEN_TTL_SECONDS)
    return token


def refresh_access_token(refresh_token: str) -> dict:
    key = f"auth:refresh:{stable_hash(refresh_token)}"
    raw = get_text(key)
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token 无效或已过期")
    data = json.loads(raw)
    user_id = data.get("user_id")

    with get_db() as db:
        user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")

    # Rotation：吊销旧 refresh token，发放新双 token
    try:
        get_redis().delete(key)
    except Exception:
        pass

    return {
        "access_token": create_access_token(user),
        "refresh_token": create_refresh_token(user),
        "token_type": "bearer",
        "user": user_to_dict(user),
    }


# ── Token 吊销 / 登出 ──────────────────────────────────────────────────────────

def _is_token_blocked(token: str) -> bool:
    return get_text(f"auth:blocklist:{stable_hash(token)}") is not None


def _block_token(token: str) -> None:
    try:
        payload = json.loads(_b64decode(token.split(".", 1)[0]))
        remaining = int(payload.get("exp", 0)) - int(datetime.now(timezone.utc).timestamp())
        if remaining > 0:
            set_text(f"auth:blocklist:{stable_hash(token)}", "1", remaining)
    except Exception:
        pass


def logout(token: str) -> None:
    _block_token(token)


# ── 邮箱验证 ──────────────────────────────────────────────────────────────────

def send_verification_email_for_user(user_id: str, email: str) -> None:
    from app.shared.email import send_verification_email
    token = secrets.token_urlsafe(32)
    set_text(f"auth:verify_email:{token}", json.dumps({"user_id": user_id, "email": email}), EMAIL_TOKEN_TTL_SECONDS)
    send_verification_email(email, token)


def verify_email_token(token: str) -> None:
    key = f"auth:verify_email:{token}"
    raw = get_text(key)
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证链接无效或已过期")
    data = json.loads(raw)
    now = datetime.now(timezone.utc)
    with get_db() as db:
        user = db.get(User, data["user_id"])
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        user.email_verified = True
        user.updated_at = now
        db.commit()
    try:
        get_redis().delete(key)
    except Exception:
        pass


# ── 密码重置 ──────────────────────────────────────────────────────────────────

def request_password_reset(email: str) -> None:
    from app.shared.email import send_password_reset_email
    normalized = _normalize_email(email)
    with get_db() as db:
        user = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
    if user is None:
        return  # 不泄露邮箱是否注册
    token = secrets.token_urlsafe(32)
    set_text(f"auth:reset_pwd:{token}", json.dumps({"user_id": user.user_id}), RESET_TOKEN_TTL_SECONDS)
    send_password_reset_email(normalized, token)


def reset_password_with_token(token: str, new_password: str) -> None:
    key = f"auth:reset_pwd:{token}"
    raw = get_text(key)
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="重置链接无效或已过期")
    data = json.loads(raw)
    now = datetime.now(timezone.utc)
    with get_db() as db:
        user = db.get(User, data["user_id"])
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        user.password_hash = hash_password(new_password)
        user.updated_at = now
        db.commit()
    try:
        get_redis().delete(key)
    except Exception:
        pass


# ── 修改密码 / 邮箱 ──────────────────────────────────────────────────────────

def change_password(user_id: str, current_password: str, new_password: str, current_token: str) -> None:
    now = datetime.now(timezone.utc)
    with get_db() as db:
        user = db.get(User, user_id)
        if user is None or not verify_password(current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="当前密码错误")
        user.password_hash = hash_password(new_password)
        user.updated_at = now
        db.commit()
    _block_token(current_token)
    delete_pattern("cache:user_auth:*")


def request_email_change(user_id: str, current_password: str, new_email: str) -> None:
    from app.shared.email import send_change_email_verification
    normalized = _normalize_email(new_email)
    with get_db() as db:
        user = db.get(User, user_id)
        if user is None or not verify_password(current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="密码错误")
        existing = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已被使用")
    token = secrets.token_urlsafe(32)
    set_text(f"auth:change_email:{token}", json.dumps({"user_id": user_id, "new_email": normalized}), EMAIL_TOKEN_TTL_SECONDS)
    send_change_email_verification(normalized, token)


def confirm_email_change(token: str) -> None:
    key = f"auth:change_email:{token}"
    raw = get_text(key)
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="确认链接无效或已过期")
    data = json.loads(raw)
    now = datetime.now(timezone.utc)
    with get_db() as db:
        user = db.get(User, data["user_id"])
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        existing = db.execute(select(User).where(User.email == data["new_email"])).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已被使用")
        user.email = data["new_email"]
        user.email_verified = True
        user.updated_at = now
        db.commit()
    try:
        get_redis().delete(key)
    except Exception:
        pass
    delete_pattern("cache:user_auth:*")


# ── 注册 / 登录 ───────────────────────────────────────────────────────────────

def register_user(username: str, email: str, password: str) -> dict:
    from concurrent.futures import ThreadPoolExecutor
    _email_executor = ThreadPoolExecutor(max_workers=1)

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
            email_verified=False,
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
    _email_executor.submit(send_verification_email_for_user, user.user_id, normalized_email)
    return {
        "access_token": create_access_token(user),
        "refresh_token": create_refresh_token(user),
        "user": user_to_dict(user),
    }


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
        if REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="请先验证邮箱后再登录",
            )

    return {
        "access_token": create_access_token(user),
        "refresh_token": create_refresh_token(user),
        "user": user_to_dict(user),
    }


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
                    email_verified=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            user.username = username
            user.email = email
            user.password_hash = hash_password(BUILTIN_PASSWORD)
            user.email_verified = True
            user.updated_at = now
        db.commit()


def delete_user_account(user_id: str, password: str) -> None:
    from sqlalchemy import text as sa_text

    with get_db() as db:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        if not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="密码错误")

        doc_ids = [r[0] for r in db.execute(
            sa_text("SELECT doc_id FROM documents WHERE user_id = :uid"), {"uid": user_id}
        ).fetchall()]
        run_ids = [r[0] for r in db.execute(
            sa_text("SELECT run_id FROM workflow_runs WHERE user_id = :uid"), {"uid": user_id}
        ).fetchall()]
        qa_ids = [r[0] for r in db.execute(
            sa_text("SELECT qa_id FROM qa_records WHERE user_id = :uid"), {"uid": user_id}
        ).fetchall()]

        if qa_ids:
            db.execute(sa_text("DELETE FROM qa_references WHERE qa_id IN :ids"), {"ids": tuple(qa_ids)})
        if run_ids:
            db.execute(sa_text("DELETE FROM workflow_steps WHERE run_id IN :ids"), {"ids": tuple(run_ids)})
        if doc_ids:
            db.execute(sa_text("DELETE FROM embedding_records WHERE doc_id IN :ids"), {"ids": tuple(doc_ids)})
            db.execute(sa_text("DELETE FROM chunk_knowledge_points WHERE doc_id IN :ids"), {"ids": tuple(doc_ids)})
            db.execute(sa_text("DELETE FROM chunks WHERE doc_id IN :ids"), {"ids": tuple(doc_ids)})
            db.execute(sa_text("DELETE FROM document_versions WHERE doc_id IN :ids"), {"ids": tuple(doc_ids)})

        db.execute(sa_text("DELETE FROM event_log WHERE user_id = :uid"), {"uid": user_id})
        db.execute(sa_text("DELETE FROM tool_call_logs WHERE user_id = :uid"), {"uid": user_id})
        db.execute(sa_text("DELETE FROM llm_call_logs WHERE user_id = :uid"), {"uid": user_id})
        db.execute(sa_text("DELETE FROM workflow_runs WHERE user_id = :uid"), {"uid": user_id})
        db.execute(sa_text("DELETE FROM review_records WHERE user_id = :uid"), {"uid": user_id})
        db.execute(sa_text("DELETE FROM study_status_history WHERE user_id = :uid"), {"uid": user_id})
        db.execute(sa_text("DELETE FROM study_records WHERE user_id = :uid"), {"uid": user_id})
        db.execute(sa_text("DELETE FROM qa_records WHERE user_id = :uid"), {"uid": user_id})
        db.execute(sa_text("DELETE FROM documents WHERE user_id = :uid"), {"uid": user_id})
        db.execute(sa_text("DELETE FROM users WHERE user_id = :uid"), {"uid": user_id})
        db.commit()


def export_user_data(user_id: str) -> dict:
    from sqlalchemy import text as sa_text

    def rows(db, sql, params=None):
        return [dict(r) for r in db.execute(sa_text(sql), params or {}).mappings().all()]

    with get_db() as db:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        return {
            "export_version": "1.0",
            "user": user_to_dict(user),
            "documents": rows(db, "SELECT * FROM documents WHERE user_id = :uid", {"uid": user_id}),
            "study_records": rows(db, "SELECT * FROM study_records WHERE user_id = :uid", {"uid": user_id}),
            "study_status_history": rows(db, "SELECT * FROM study_status_history WHERE user_id = :uid", {"uid": user_id}),
            "qa_records": rows(db, "SELECT * FROM qa_records WHERE user_id = :uid", {"uid": user_id}),
            "review_records": rows(db, "SELECT * FROM review_records WHERE user_id = :uid", {"uid": user_id}),
            "workflow_runs": rows(db, "SELECT * FROM workflow_runs WHERE user_id = :uid", {"uid": user_id}),
            "llm_call_logs": rows(db, "SELECT * FROM llm_call_logs WHERE user_id = :uid", {"uid": user_id}),
            "tool_call_logs": rows(db, "SELECT * FROM tool_call_logs WHERE user_id = :uid", {"uid": user_id}),
        }


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    token = credentials.credentials

    if _is_token_blocked(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 已失效，请重新登录")

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
            email_verified=cached.get("email_verified", True),
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
            "email_verified": user.email_verified,
        }
        set_json(cache_key, cached_user, USER_CACHE_TTL_SECONDS)
        return user
