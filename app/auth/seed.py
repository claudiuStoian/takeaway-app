from pathlib import Path

from pydantic import TypeAdapter
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.auth.schemas import UserSeed
from app.core.config import Environment
from app.core.exceptions import ConflictError
from app.core.security import password_hash

SEED_FILE_ADAPTER = TypeAdapter(list[UserSeed])


class NonAdminUserExists(ConflictError):
    detail = 'A non-admin user with this email already exists.'


class UserSeedService:
    """Sync, for the CLI: argon2 runs inline because there is no event loop to block."""

    @classmethod
    def seed_demo_users_if_empty(
        cls, session: Session, seed_file: Path, environment: Environment
    ) -> int:
        """Inserts the demo users unless any user exists; returns how many were added.

        Demo passwords are public, so they are never seeded in production.
        """
        if environment == Environment.PRODUCTION or cls._has_users(session):
            return 0
        users = cls._load(seed_file)
        session.add_all(cls._build_user(seed) for seed in users)
        session.commit()
        return len(users)

    @classmethod
    def create_admin(cls, session: Session, seed: UserSeed) -> bool:
        """Returns False when the admin already exists; never changes an existing user."""
        existing = session.scalar(select(User).where(User.email == seed.email))
        if existing is not None:
            if existing.role != UserRole.ADMIN:
                raise NonAdminUserExists
            return False
        session.add(cls._build_user(seed))
        session.commit()
        return True

    @staticmethod
    def _has_users(session: Session) -> bool:
        return session.scalar(select(exists().select_from(User))) or False

    @staticmethod
    def _load(seed_file: Path) -> list[UserSeed]:
        return SEED_FILE_ADAPTER.validate_json(seed_file.read_bytes())

    @staticmethod
    def _build_user(seed: UserSeed) -> User:
        return User(
            email=seed.email,
            hashed_password=password_hash.hash(seed.password),
            full_name=seed.full_name,
            role=seed.role,
        )
