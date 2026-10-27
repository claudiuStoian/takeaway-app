from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi.concurrency import run_in_threadpool
from pwdlib import PasswordHash

from app.core.config import settings
from app.core.exceptions import NotAuthenticatedError

# Pinned in code so no configuration change can weaken verification (alg confusion, 'none').
JWT_ALGORITHM = 'HS256'
ACCESS_TOKEN_TTL_MINUTES = 15

password_hash = PasswordHash.recommended()


async def hash_password(password: str) -> str:
    return await run_in_threadpool(password_hash.hash, password)


async def verify_password(password: str, hashed_password: str) -> bool:
    return await run_in_threadpool(password_hash.verify, password, hashed_password)


def create_access_token(subject: UUID) -> str:
    issued_at = datetime.now(UTC)
    claims = {
        'sub': str(subject),
        'iat': issued_at,
        'exp': issued_at + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES),
    }
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token_subject(token: str) -> str:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[JWT_ALGORITHM],
            options={'require': ['exp', 'sub']},
        )
    except jwt.InvalidTokenError as exc:
        raise NotAuthenticatedError from exc
    return claims['sub']
