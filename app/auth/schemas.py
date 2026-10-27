from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.auth.models import UserRole
from app.core.security import ACCESS_TOKEN_TTL_MINUTES

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
MAX_FULL_NAME_LENGTH = 100

NormalizedEmail = Annotated[EmailStr, AfterValidator(str.lower)]
NewPassword = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]
FullName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_FULL_NAME_LENGTH)
]


class SignupRequest(BaseModel):
    """Has no role field: signup always creates a customer, whatever the client sends."""

    email: NormalizedEmail
    password: NewPassword
    full_name: FullName


class LoginRequest(BaseModel):
    email: NormalizedEmail
    # Bounded so an oversized password can't make argon2 do unbounded work.
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


class TokenRead(BaseModel):
    access_token: str
    token_type: Literal['bearer'] = 'bearer'
    expires_in: int = ACCESS_TOKEN_TTL_MINUTES * 60


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    email: str
    full_name: str
    role: UserRole
    created_at: datetime


class UserSeed(BaseModel):
    # Validation errors would otherwise echo the password.
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)

    email: NormalizedEmail
    password: NewPassword
    full_name: FullName
    role: UserRole
