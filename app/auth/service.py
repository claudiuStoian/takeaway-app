from logging import getLogger
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.auth.schemas import LoginRequest, SignupRequest, TokenRead, UserRead
from app.core.exceptions import ConflictError, NotAuthenticatedError
from app.core.security import (
    create_access_token,
    decode_access_token_subject,
    hash_password,
    password_hash,
    verify_password,
)

logger = getLogger(__name__)

EMAIL_UNIQUE_CONSTRAINT = 'uq_users_email'

# Verified against when the email is unknown, so a miss takes as long as a wrong password.
DUMMY_PASSWORD_HASH = password_hash.hash('dummy-password-for-timing')


class EmailAlreadyRegistered(ConflictError):
    detail = 'Email already registered.'


class InvalidCredentials(NotAuthenticatedError):
    detail = 'Invalid email or password.'


class AuthService:
    @classmethod
    async def signup(cls, session: AsyncSession, request: SignupRequest) -> UserRead:
        user = User(
            email=request.email,
            hashed_password=await hash_password(request.password),
            full_name=request.full_name,
            role=UserRole.CUSTOMER,
        )
        session.add(user)
        await cls._commit_new_user(session)
        return UserRead.model_validate(user)

    @classmethod
    async def login(cls, session: AsyncSession, request: LoginRequest) -> TokenRead:
        user = await session.scalar(select(User).where(User.email == request.email))
        if not await cls._is_valid_login(user, request.password):
            logger.warning('Login failed')
            raise InvalidCredentials
        return TokenRead(access_token=create_access_token(user.public_id))

    @classmethod
    async def authenticate(cls, session: AsyncSession, token: str) -> User:
        """Returns the active user a valid access token belongs to; role is read from the DB."""
        subject = decode_access_token_subject(token)
        user = await cls._find_by_public_id(session, subject)
        if user is None or not user.is_active:
            raise NotAuthenticatedError
        return user

    @staticmethod
    async def _commit_new_user(session: AsyncSession) -> None:
        # The unique constraint decides duplicates, so two concurrent signups can't both pass.
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            if exc.orig.diag.constraint_name == EMAIL_UNIQUE_CONSTRAINT:
                raise EmailAlreadyRegistered from exc
            raise

    @staticmethod
    async def _is_valid_login(user: User | None, password: str) -> bool:
        if user is None:
            await verify_password(password, DUMMY_PASSWORD_HASH)
            return False
        return await verify_password(password, user.hashed_password) and user.is_active

    @staticmethod
    async def _find_by_public_id(session: AsyncSession, subject: str) -> User | None:
        try:
            public_id = UUID(subject)
        except ValueError:
            return None
        return await session.scalar(select(User).where(User.public_id == public_id))
