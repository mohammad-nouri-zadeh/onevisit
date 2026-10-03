"""Creazione di engine e sessioni. La URL arriva sempre dall'applicazione chiamante."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(database_url: str) -> Engine:
    """Crea un engine con controllo delle connessioni prima dell'uso."""
    return create_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Crea la factory delle sessioni; ``expire_on_commit=False`` evita letture implicite."""
    return sessionmaker(bind=engine, expire_on_commit=False)
