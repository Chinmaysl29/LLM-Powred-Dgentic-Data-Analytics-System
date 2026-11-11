"""Explicit hosted database targeting; browser keys never authorize SQL access."""
import re
from urllib.parse import urlsplit

from sqlalchemy import event
from sqlalchemy.engine import make_url


def hosted_postgres_dsn(value: str, project_url: str) -> str:
    try:
        url = make_url(value)
    except Exception:
        raise ValueError('SUPABASE_DATABASE_URL must be a PostgreSQL connection URI, not an HTTPS API URL.') from None
    if url.get_backend_name() not in {'postgres', 'postgresql'} or not url.username or not url.password:
        raise ValueError('SUPABASE_DATABASE_URL requires a PostgreSQL username and database password.')
    project = (urlsplit(project_url).hostname or '').split('.')[0]
    direct = url.host == f'db.{project}.supabase.co'
    pooled = bool(url.host and url.host.endswith('.pooler.supabase.com') and url.username.endswith('.' + project))
    if not project or not (direct or pooled):
        raise ValueError('The database connection must belong to the configured Supabase project.')
    if url.port not in {None, 5432}:
        raise ValueError('Use the direct or Session pooler connection on port 5432, not transaction pooling.')
    return url.set(drivername='postgresql+psycopg').update_query_dict(
        {'sslmode': 'require', 'connect_timeout': '10'},
    ).render_as_string(hide_password=False)


def bind_database_schema(engine, schema: str) -> None:
    """Set search_path before dialect initialization, without URL startup options.

    Session pooling preserves it. Never fall through into Supabase public tables
    which use a different schema and ownership model from the FastAPI database.
    """
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema):
        raise ValueError('Invalid database schema identifier')
    if schema == 'public':
        return

    def configure(connection, _record):
        previous = connection.autocommit
        connection.autocommit = True
        try:
            with connection.cursor() as cursor:
                cursor.execute(f'SET SESSION search_path = "{schema}"')
                cursor.execute("SET TIME ZONE 'UTC'")
        finally:
            connection.autocommit = previous

    event.listen(engine, 'connect', configure, insert=True)
