from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from scrapers.config import settings

# `connect_args.options` ajusta `statement_timeout` por sesión: Supabase free
# tier impone 8 segundos por default, demasiado corto para inserts con index
# updates en una tabla grande con scrapers en paralelo.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"options": "-c statement_timeout=120000 -c lock_timeout=30000"},
)


@event.listens_for(engine, "connect")
def _set_session_params(dbapi_connection, _connection_record) -> None:
    """Por si el `options` no llega (algunos poolers lo droppean)."""
    cur = dbapi_connection.cursor()
    try:
        cur.execute("SET statement_timeout = '120s'; SET lock_timeout = '30s';")
        dbapi_connection.commit()
    except Exception:
        dbapi_connection.rollback()
    finally:
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
