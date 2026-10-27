from http import HTTPStatus

from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Base for errors services raise; mapped to HTTP responses by one handler."""

    status_code: HTTPStatus = HTTPStatus.BAD_REQUEST
    detail: str = 'The request could not be processed.'

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class NotFoundError(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    detail = 'Not found.'


class ConflictError(DomainError):
    status_code = HTTPStatus.CONFLICT
    detail = 'The request conflicts with the current state.'


class InvalidInputError(DomainError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    detail = 'Invalid input.'


async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={'detail': exc.detail})
