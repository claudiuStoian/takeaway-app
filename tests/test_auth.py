from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import JWT_ALGORITHM
from tests.builders import TEST_PASSWORD, deactivate_user, signup_and_login

pytestmark = pytest.mark.anyio

ACCESS_TOKEN_TTL_SECONDS = 15 * 60
CLOCK_TOLERANCE_SECONDS = 5

USER_KEYS = {'public_id', 'email', 'full_name', 'role', 'created_at'}


def new_email() -> str:
    return f'{uuid4()}@example.com'


async def signup(client: AsyncClient, email: str, **extra: str) -> Response:
    return await client.post(
        '/api/v1/auth/signup',
        json={'email': email, 'password': TEST_PASSWORD, 'full_name': 'Ada Lovelace', **extra},
    )


async def test_signup_creates_a_customer_and_returns_only_public_fields(
    client: AsyncClient,
) -> None:
    email = new_email()

    response = await signup(client, email)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == USER_KEYS
    assert body['email'] == email
    assert body['full_name'] == 'Ada Lovelace'
    assert body['role'] == 'customer'


async def test_signup_ignores_a_requested_admin_role(client: AsyncClient) -> None:
    response = await signup(client, new_email(), role='admin')

    assert response.status_code == 201
    assert response.json()['role'] == 'customer'


async def test_email_is_case_insensitive(client: AsyncClient) -> None:
    local_part = uuid4().hex
    first = await signup(client, f'{local_part.upper()}@EXAMPLE.com')

    duplicate = await signup(client, f'{local_part}@example.com')
    login = await client.post(
        '/api/v1/auth/login',
        json={'email': f'{local_part}@Example.COM', 'password': TEST_PASSWORD},
    )

    assert first.status_code == 201
    assert first.json()['email'] == f'{local_part}@example.com'
    assert duplicate.status_code == 409
    assert login.status_code == 200


@pytest.mark.parametrize(
    'overrides',
    [
        {'password': 'x' * 7},
        {'password': 'x' * 129},
        {'email': 'not-an-email'},
        {'full_name': '   '},
    ],
    ids=['password-too-short', 'password-too-long', 'bad-email', 'blank-name'],
)
async def test_signup_rejects_invalid_input(client: AsyncClient, overrides: dict) -> None:
    body = {'email': new_email(), 'password': TEST_PASSWORD, 'full_name': 'Ada', **overrides}

    response = await client.post('/api/v1/auth/signup', json=body)

    assert response.status_code == 422


async def test_login_returns_a_15_minute_bearer_token(client: AsyncClient) -> None:
    email = new_email()
    await signup(client, email)

    response = await client.post(
        '/api/v1/auth/login', json={'email': email, 'password': TEST_PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body['token_type'] == 'bearer'
    assert body['expires_in'] == ACCESS_TOKEN_TTL_SECONDS
    claims = jwt.decode(body['access_token'], options={'verify_signature': False})
    expected_expiry = datetime.now(UTC).timestamp() + ACCESS_TOKEN_TTL_SECONDS
    assert abs(claims['exp'] - expected_expiry) <= CLOCK_TOLERANCE_SECONDS


async def test_wrong_password_and_unknown_email_get_the_same_401(client: AsyncClient) -> None:
    email = new_email()
    await signup(client, email)

    wrong_password = await client.post(
        '/api/v1/auth/login', json={'email': email, 'password': 'wrong-password'}
    )
    unknown_email = await client.post(
        '/api/v1/auth/login', json={'email': new_email(), 'password': TEST_PASSWORD}
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


async def test_me_returns_the_logged_in_user(client: AsyncClient) -> None:
    email = new_email()
    headers = await signup_and_login(client, email)

    response = await client.get('/api/v1/me', headers=headers)

    assert response.status_code == 200
    assert set(response.json()) == USER_KEYS
    assert response.json()['email'] == email


async def test_me_without_a_token_is_401(client: AsyncClient) -> None:
    response = await client.get('/api/v1/me')

    assert response.status_code == 401


async def test_tampered_token_is_401(client: AsyncClient) -> None:
    headers = await signup_and_login(client)
    token = headers['Authorization'].removeprefix('Bearer ')
    header, payload, signature = token.split('.')
    flipped = ('B' if signature[0] == 'A' else 'A') + signature[1:]

    response = await client.get(
        '/api/v1/me', headers={'Authorization': f'Bearer {header}.{payload}.{flipped}'}
    )

    assert response.status_code == 401


async def test_expired_token_is_401(client: AsyncClient) -> None:
    email = new_email()
    public_id = (await signup(client, email)).json()['public_id']
    issued_at = datetime.now(UTC) - timedelta(hours=1)
    expired = jwt.encode(
        {'sub': public_id, 'iat': issued_at, 'exp': issued_at + timedelta(minutes=15)},
        settings.jwt_secret_key,
        algorithm=JWT_ALGORITHM,
    )

    response = await client.get('/api/v1/me', headers={'Authorization': f'Bearer {expired}'})

    assert response.status_code == 401


async def test_token_without_an_expiry_is_401(client: AsyncClient) -> None:
    public_id = (await signup(client, new_email())).json()['public_id']
    token = jwt.encode({'sub': public_id}, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)

    response = await client.get('/api/v1/me', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 401


async def test_token_for_an_unknown_user_is_401(client: AsyncClient) -> None:
    token = jwt.encode(
        {'sub': str(uuid4()), 'exp': datetime.now(UTC) + timedelta(minutes=15)},
        settings.jwt_secret_key,
        algorithm=JWT_ALGORITHM,
    )

    response = await client.get('/api/v1/me', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 401


async def test_deactivated_user_is_rejected_with_a_still_valid_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    email = new_email()
    headers = await signup_and_login(client, email)

    await deactivate_user(db_session, email)
    response = await client.get('/api/v1/me', headers=headers)

    assert response.status_code == 401


async def test_deactivated_user_cannot_log_in(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    email = new_email()
    await signup(client, email)
    wrong_password = await client.post(
        '/api/v1/auth/login', json={'email': email, 'password': 'wrong-password'}
    )

    await deactivate_user(db_session, email)
    response = await client.post(
        '/api/v1/auth/login', json={'email': email, 'password': TEST_PASSWORD}
    )

    assert response.status_code == 401
    assert response.json() == wrong_password.json()
