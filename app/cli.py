"""Operational commands: `python -m app.cli <command>`."""

import argparse
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from getpass import getpass
from logging import getLogger
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth.models import UserRole
from app.auth.schemas import UserSeed
from app.auth.seed import NonAdminUserExists, UserSeedService
from app.core.config import settings
from app.restaurants.seed import CatalogueSeedService

SEED_DIR = Path(__file__).resolve().parents[1] / 'seed'
RESTAURANTS_SEED_FILE = SEED_DIR / 'restaurants.json'
USERS_SEED_FILE = SEED_DIR / 'users.json'

logger = getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog='python -m app.cli')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('seed', help='Insert demo restaurants and users into empty tables.')
    create_admin_parser = commands.add_parser(
        'create-admin', help='Create an admin user; prompts for the password.'
    )
    create_admin_parser.add_argument('--email', required=True)
    create_admin_parser.add_argument('--full-name', required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s [%(name)s] %(message)s')
    match args.command:
        case 'seed':
            seed()
        case 'create-admin':
            create_admin(args.email, args.full_name)


def seed() -> None:
    with _open_session() as session:
        restaurants_added = CatalogueSeedService.seed_if_empty(session, RESTAURANTS_SEED_FILE)
        users_added = UserSeedService.seed_demo_users_if_empty(
            session, USERS_SEED_FILE, settings.environment
        )
    if restaurants_added:
        logger.info('Seeded %d restaurants.', restaurants_added)
    else:
        logger.info('Restaurants already present; seed skipped.')
    if users_added:
        logger.info('Seeded %d demo users.', users_added)
    else:
        logger.info('Users already present or ENVIRONMENT=production; demo users skipped.')


def create_admin(email: str, full_name: str) -> None:
    password = getpass('Password: ')
    if getpass('Repeat password: ') != password:
        sys.exit('Passwords do not match; nothing changed.')
    try:
        admin = UserSeed(email=email, password=password, full_name=full_name, role=UserRole.ADMIN)
    except ValidationError as exc:
        sys.exit(f'Invalid admin details; nothing changed.\n{exc}')

    with _open_session() as session:
        try:
            created = UserSeedService.create_admin(session, admin)
        except NonAdminUserExists as exc:
            sys.exit(f'{exc.detail} Nothing changed.')
    logger.info('Admin created.' if created else 'Admin already exists; nothing changed.')


@contextmanager
def _open_session() -> Iterator[Session]:
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
