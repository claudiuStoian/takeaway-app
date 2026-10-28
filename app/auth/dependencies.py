from logging import getLogger
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.models import User, UserRole
from app.auth.service import AuthService
from app.core.db import SessionDep
from app.core.exceptions import ForbiddenError, NotAuthenticatedError

logger = getLogger(__name__)

# auto_error=False so a missing token raises our NotAuthenticatedError, same shape as a bad one.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise NotAuthenticatedError
    return await AuthService.authenticate(session, credentials.credentials)


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUserDep) -> User:
    if user.role != UserRole.ADMIN:
        logger.warning('Admin access denied')
        raise ForbiddenError
    return user


AdminDep = Annotated[User, Depends(require_admin)]
