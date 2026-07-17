import re


def plain_dsn(url: str) -> str:
    """Strip a SQLAlchemy '+driver' from the URL scheme so psycopg2/asyncpg accept it.

    Args:
        url: A database URL, possibly like 'postgresql+asyncpg://...'.
    Returns:
        The same URL with any '+driver' removed from the scheme.
    """
    return re.sub(r"^(postgresql|postgres)\+\w+://", r"\1://", url)
