from fastapi import APIRouter, status

from app.auth.dependencies import CurrentUserDep
from app.auth.schemas import LoginRequest, SignupRequest, TokenResponse, UserResponse
from app.auth.service import AuthService
from app.core.db import SessionDep

router = APIRouter(tags=['auth'])


@router.post('/auth/signup', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(session: SessionDep, request: SignupRequest) -> UserResponse:
    return await AuthService.signup(session, request)


@router.post('/auth/login', response_model=TokenResponse)
async def login(session: SessionDep, request: LoginRequest) -> TokenResponse:
    return await AuthService.login(session, request)


@router.get('/me', response_model=UserResponse)
async def read_me(user: CurrentUserDep) -> UserResponse:
    return UserResponse.model_validate(user)
