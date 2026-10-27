from logging import getLogger

from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import SessionDep

logger = getLogger(__name__)

router = APIRouter(tags=['health'])


@router.get('/health')
async def health(session: SessionDep, response: Response) -> dict[str, str]:
    try:
        await session.execute(text('SELECT 1'))
    except DBAPIError:
        logger.warning('Health check failed: database unreachable')
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {'status': 'unavailable'}
    return {'status': 'ok'}
