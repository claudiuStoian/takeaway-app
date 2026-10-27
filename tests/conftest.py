from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import AppSettings, settings
from app.core.db import get_session
from app.main import app

TEST_DB_NAME = 'takeaway_test'
ALEMBIC_INI = Path(__file__).resolve().parents[1] / 'alembic.ini'

test_settings = settings.model_copy(update={'db_name': TEST_DB_NAME})


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        '--create-db',
        action='store_true',
        help=f'Drop and recreate the {TEST_DB_NAME} database before running tests.',
    )


@pytest.fixture(scope='session')
def anyio_backend() -> str:
    return 'asyncio'


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
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


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
    config.set_main_option('sqlalchemy.url', db_settings.database_url.replace('%', '%%'))
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
