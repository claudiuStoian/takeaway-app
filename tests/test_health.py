from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.db import get_session
from app.main import app

pytestmark = pytest.mark.anyio

UNREACHABLE_DB_PORT = 1


async def test_health_is_ok_when_database_answers(client: AsyncClient) -> None:
    response = await client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


async def test_health_is_503_when_database_is_unreachable(client: AsyncClient) -> None:
    unreachable = settings.model_copy(update={'db_port': UNREACHABLE_DB_PORT})
    engine = create_async_engine(unreachable.database_url, poolclass=NullPool)

    async def unreachable_session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(engine) as session:
            yield session

    app.dependency_overrides[get_session] = unreachable_session
    try:
        response = await client.get('/health')
    finally:
        await engine.dispose()

    assert response.status_code == 503
    assert response.json() == {'status': 'unavailable'}
