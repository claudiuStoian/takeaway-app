from fastapi import APIRouter, status

from app.auth.dependencies import CurrentUserDep
from app.auth.schemas import LoginRequest, SignupRequest, TokenRead, UserRead
from app.auth.service import AuthService
from app.core.db import SessionDep

router = APIRouter(tags=['auth'])


@router.post('/auth/signup', response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def signup(session: SessionDep, request: SignupRequest) -> UserRead:
    return await AuthService.signup(session, request)


@router.post('/auth/login', response_model=TokenRead)
async def login(session: SessionDep, request: LoginRequest) -> TokenRead:
    return await AuthService.login(session, request)


@router.get('/me', response_model=UserRead)
async def read_me(user: CurrentUserDep) -> UserRead:
    return UserRead.model_validate(user)
