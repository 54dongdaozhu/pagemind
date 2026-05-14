from fastapi import APIRouter, Depends

from app.core.database import User
from app.modules.auth.schemas import AuthResponse, UserCreate, UserLogin, UserOut
from app.modules.auth.service import get_current_user, login_user, register_user, user_to_dict


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
