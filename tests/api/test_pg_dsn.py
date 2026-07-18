from api.pg_dsn import plain_dsn


def test_strips_asyncpg_driver():
    assert plain_dsn("postgresql+asyncpg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"


def test_strips_psycopg2_driver():
    assert plain_dsn("postgresql+psycopg2://u:p@h/db") == "postgresql://u:p@h/db"


def test_passthrough_when_no_driver():
    assert plain_dsn("postgresql://u:p@h/db") == "postgresql://u:p@h/db"
