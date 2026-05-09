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


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
