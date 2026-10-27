from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth
from app.core import health
from app.core.config import settings
from app.core.db import engine
from app.core.exceptions import DomainError, handle_domain_error
from app.orders import admin_router as admin_orders
from app.orders import router as orders
from app.restaurants import router as restaurants

API_PREFIX = '/api/v1'


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(title='Takeaway API', lifespan=lifespan)
app.add_exception_handler(DomainError, handle_domain_error)
app.include_router(health.router)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(restaurants.router, prefix=API_PREFIX)
app.include_router(orders.router, prefix=API_PREFIX)
app.include_router(admin_orders.router, prefix=API_PREFIX)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=['*'],
        allow_headers=['*'],
    )
