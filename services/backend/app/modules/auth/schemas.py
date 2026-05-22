from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=128)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    account: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    user_id: str
    username: str
    email: str
    email_verified: bool


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ChangeEmailRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_email: str = Field(min_length=3, max_length=255)


class RefreshTokenRequest(BaseModel):
    refresh_token: str
