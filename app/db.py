"""SQLAlchemy engine and session helpers (data tier only)."""

from flask import current_app, g
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def get_engine():
    return current_app.engine


def get_session():
    if "db_session" not in g:
        Session = sessionmaker(bind=get_engine())
        g.db_session = Session()
    return g.db_session


def close_session(exception=None):
    session = g.pop("db_session", None)
    if session is not None:
        if exception is not None:
            session.rollback()
        session.close()
