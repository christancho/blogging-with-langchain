from api.pg_dsn import async_dsn, plain_dsn


def test_strips_asyncpg_driver():
    assert plain_dsn("postgresql+asyncpg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"


def test_strips_psycopg2_driver():
    assert plain_dsn("postgresql+psycopg2://u:p@h/db") == "postgresql://u:p@h/db"


def test_passthrough_when_no_driver():
    assert plain_dsn("postgresql://u:p@h/db") == "postgresql://u:p@h/db"


def test_async_dsn_rewrites_bare_postgres_scheme():
    assert async_dsn("postgres://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"


def test_async_dsn_adds_driver_to_postgresql_scheme():
    assert async_dsn("postgresql://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"


def test_async_dsn_passthrough_when_driver_already_specified():
    assert async_dsn("postgresql+asyncpg://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"
