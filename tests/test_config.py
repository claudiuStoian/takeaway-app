from sqlalchemy import make_url

from app.core.config import settings


def test_database_url_keeps_a_password_with_url_characters() -> None:
    password = 'p@ss:w/rd%?#'
    url = settings.model_copy(update={'db_password': password}).database_url

    parsed = make_url(url.render_as_string(hide_password=False))

    assert (parsed.password, parsed.host, parsed.database) == (
        password,
        settings.db_host,
        settings.db_name,
    )
