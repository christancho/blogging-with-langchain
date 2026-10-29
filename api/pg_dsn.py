import re


def plain_dsn(url: str) -> str:
    """Strip a SQLAlchemy '+driver' from the URL scheme so psycopg2/asyncpg accept it.

    Args:
        url: A database URL, possibly like 'postgresql+asyncpg://...'.
    Returns:
        The same URL with any '+driver' removed from the scheme.
    """
    return re.sub(r"^(postgresql|postgres)\+\w+://", r"\1://", url)


def async_dsn(url: str) -> str:
    """Normalize a DATABASE_URL to 'postgresql+asyncpg://', SQLAlchemy's async engine.

    Some managed Postgres providers hand out URLs with the bare 'postgres://'
    scheme; SQLAlchemy has no dialect named 'postgres' (only 'postgresql'), so
    that scheme fails to load. This rewrites 'postgres://' to 'postgresql://'
    and adds the '+asyncpg' driver when no driver is already specified.

    Args:
        url: A database URL, e.g. 'postgres://...' or 'postgresql://...'.
    Returns:
        The URL with scheme 'postgresql+asyncpg://', unless a driver was
        already specified, in which case it's left as-is.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url
