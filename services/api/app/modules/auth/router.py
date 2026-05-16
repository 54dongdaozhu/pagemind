from fastapi import APIRouter, Depends, Query, Request

from app.core.database import User
from app.modules.auth.schemas import (
    AuthResponse,
    ChangeEmailRequest,
    ChangePasswordRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    UserCreate,
    UserLogin,
    UserOut,
)
from app.modules.auth.service import (
    change_password,
    confirm_email_change,
    delete_user_account,
    export_user_data,
    get_current_user,
    login_user,
    logout,
    refresh_access_token,
    register_user,
    request_email_change,
    request_password_reset,
    reset_password_with_token,
    send_verification_email_for_user,
    user_to_dict,
    verify_email_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
def register(request: UserCreate):
    return register_user(request.username, request.email, request.password)


@router.post("/login", response_model=AuthResponse)
def login(request: UserLogin):
    return login_user(request.account, request.password)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return user_to_dict(current_user)


@router.delete("/me")
def delete_account(body: DeleteAccountRequest, current_user: User = Depends(get_current_user)):
    delete_user_account(current_user.user_id, body.password)
    return {"message": "账号已注销，所有数据已删除"}


@router.get("/me/export")
def export_data(current_user: User = Depends(get_current_user)):
    return export_user_data(current_user.user_id)


# ── 邮箱验证 ──────────────────────────────────────────────────────────────────

@router.post("/send-verification")
def send_verification(current_user: User = Depends(get_current_user)):
    send_verification_email_for_user(current_user.user_id, current_user.email)
    return {"message": "验证邮件已发送"}


@router.get("/verify-email")
def verify_email(token: str = Query(...)):
    verify_email_token(token)
    return {"message": "邮箱验证成功"}


# ── 密码重置 ──────────────────────────────────────────────────────────────────

@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest):
    request_password_reset(body.email)
    return {"message": "如果该邮箱已注册，重置邮件已发送"}


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest):
    reset_password_with_token(body.token, body.new_password)
    return {"message": "密码重置成功，请重新登录"}


# ── 修改账号信息 ──────────────────────────────────────────────────────────────

@router.patch("/me/password")
def update_password(body: ChangePasswordRequest, request: Request, current_user: User = Depends(get_current_user)):
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    change_password(current_user.user_id, body.current_password, body.new_password, token)
    return {"message": "密码已更新，请重新登录"}


@router.patch("/me/email")
def update_email(body: ChangeEmailRequest, current_user: User = Depends(get_current_user)):
    request_email_change(current_user.user_id, body.current_password, body.new_email)
    return {"message": "验证邮件已发送至新邮箱，确认后生效"}


@router.get("/verify-email-change")
def verify_email_change(token: str = Query(...)):
    confirm_email_change(token)
    return {"message": "邮箱已更新"}


# ── Token 管理 ────────────────────────────────────────────────────────────────

@router.post("/logout")
def logout_endpoint(request: Request, current_user: User = Depends(get_current_user)):
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    logout(token)
    return {"message": "已登出"}


@router.post("/refresh", response_model=AuthResponse)
def refresh(body: RefreshTokenRequest):
    return refresh_access_token(body.refresh_token)
