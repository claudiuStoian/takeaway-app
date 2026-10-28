import json
from base64 import urlsafe_b64decode, urlsafe_b64encode

from app.core.exceptions import InvalidInputError

DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100


class InvalidCursor(InvalidInputError):
    detail = 'Invalid cursor.'


def encode_cursor(values: list[str | int]) -> str:
    """Encodes the last row's sort key. Base64 is not secrecy: put only public values in it."""
    return urlsafe_b64encode(json.dumps(values).encode()).decode()


def decode_cursor(cursor: str, expected_types: tuple[type, ...]) -> list[str | int]:
    try:
        values = json.loads(urlsafe_b64decode(cursor.encode()))
    except ValueError as exc:
        raise InvalidCursor from exc

    if not isinstance(values, list) or len(values) != len(expected_types):
        raise InvalidCursor
    for value, expected_type in zip(values, expected_types, strict=True):
        # Exact type check: bool is an int subclass and must not pass as an id.
        if type(value) is not expected_type:
            raise InvalidCursor
        if type(value) is int and value < 1:
            raise InvalidCursor

    return values
