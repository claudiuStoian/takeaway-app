from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from psycopg import sql
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core import security
from app.core.config import AppSettings, settings
from app.core.db import get_session
from app.main import app
from tests.builders import signup_admin_and_login, signup_and_login

TEST_DB_NAME = 'takeaway_test'
ALEMBIC_INI = Path(__file__).resolve().parents[1] / 'alembic.ini'

test_settings = settings.model_copy(update={'db_name': TEST_DB_NAME})

# Tests check the auth flow, not the hash's cost, so argon2 runs with its minimum work.
CHEAP_PASSWORD_HASH = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8, parallelism=1),))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        '--create-db',
        action='store_true',
        help=f'Drop and recreate the {TEST_DB_NAME} database before running tests.',
    )


@pytest.fixture(scope='session')
def anyio_backend() -> str:
    return 'asyncio'


def pytest_report_header(config: pytest.Config) -> str:
    if config.getoption('--create-db'):
        return f'test database: {TEST_DB_NAME} (dropped and recreated)'
    return f'test database: {TEST_DB_NAME} (kept from the last run)'


@pytest.fixture(scope='session', autouse=True)
def cheap_password_hashing() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(security, 'password_hash', CHEAP_PASSWORD_HASH)
        yield


@pytest.fixture(scope='session')
def migrated_test_db(request: pytest.FixtureRequest) -> None:
    """Ensures the kept test database exists and is at the latest migration."""
    if request.config.getoption('--create-db'):
        _drop_test_db(test_settings)
    _create_test_db_if_missing(test_settings)
    _upgrade_to_head(test_settings)


@pytest.fixture(scope='session')
async def test_engine(migrated_test_db: None) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(test_settings.database_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session inside an outer transaction that is always rolled back."""
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            join_transaction_mode='create_savepoint',
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        try:
            yield db_session
        finally:
            # Start each request with an empty identity map, like a fresh production session.
            db_session.expunge_all()

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def customer(client: AsyncClient) -> dict[str, str]:
    """Auth headers of a freshly signed-up customer."""
    return await signup_and_login(client)


@pytest.fixture
async def admin(client: AsyncClient, db_session: AsyncSession) -> dict[str, str]:
    """Auth headers of a freshly created admin."""
    return await signup_admin_and_login(client, db_session)


@pytest.fixture
async def committed_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session whose commits are real; for tests that need several concurrent sessions."""
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
async def committed_client(test_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """A client where each request gets its own session and commits for real.

    Rows it writes are kept, so tests using it must only assert on rows they created.
    """
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(scope='session')
def sync_test_engine(migrated_test_db: None) -> Iterator[Engine]:
    engine = create_engine(test_settings.database_url, poolclass=NullPool)
    yield engine
    engine.dispose()


@pytest.fixture
def sync_db_session(sync_test_engine: Engine) -> Iterator[Session]:
    """A sync session inside an outer transaction that is always rolled back."""
    with sync_test_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode='create_savepoint')
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


def _drop_test_db(db_settings: AppSettings) -> None:
    _refuse_non_test_db(db_settings.db_name)
    with _connect_to_maintenance_db(db_settings) as conn:
        conn.execute(
            sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(
                sql.Identifier(db_settings.db_name)
            )
        )


def _create_test_db_if_missing(db_settings: AppSettings) -> None:
    _refuse_non_test_db(db_settings.db_name)
    with _connect_to_maintenance_db(db_settings) as conn:
        exists = conn.execute(
            'SELECT 1 FROM pg_database WHERE datname = %s', (db_settings.db_name,)
        ).fetchone()
        if not exists:
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db_settings.db_name)))


def _upgrade_to_head(db_settings: AppSettings) -> None:
    config = Config(str(ALEMBIC_INI))
    database_url = db_settings.database_url.render_as_string(hide_password=False)
    config.set_main_option('sqlalchemy.url', database_url.replace('%', '%%'))
    config.attributes['configure_logger'] = False
    command.upgrade(config, 'head')


def _refuse_non_test_db(db_name: str) -> None:
    if not db_name.endswith('_test'):
        raise RuntimeError(f'Refusing to touch database {db_name!r}: name must end in _test.')


def _connect_to_maintenance_db(db_settings: AppSettings) -> psycopg.Connection:
    return psycopg.connect(
        host=db_settings.db_host,
        port=db_settings.db_port,
        user=db_settings.db_user,
        password=db_settings.db_password,
        dbname='postgres',
        autocommit=True,
    )
