from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.orm import ORMExecuteState, Session, sessionmaker, with_loader_criteria

from app.core.config import get_settings


@lru_cache
def get_engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


@lru_cache
def _status_models() -> tuple[type, ...]:
    from app.db.base import Base
    import app.models  # noqa: F401
    return tuple(mp.class_ for mp in Base.registry.mappers if "data_status" in mp.columns)


@event.listens_for(Session, "do_orm_execute")
def _hide_simulated(state: ORMExecuteState) -> None:
    """Sessions de l'API publique : toute ligne `simulated` (démo) est exclue des requêtes ORM, relations comprises.
    Contournement explicite possible par `execution_options(include_simulated=True)` (indicateurs système)."""
    if not state.session.info.get("hide_simulated") or state.execution_options.get("include_simulated"):
        return
    if state.is_select or state.is_relationship_load:
        state.statement = state.statement.options(*(
            with_loader_criteria(cls, lambda c: c.data_status != "simulated", include_aliases=True) for cls in _status_models()))


def get_db() -> Iterator[Session]:
    db = get_sessionmaker()()
    db.info["hide_simulated"] = not get_settings().show_simulated_data
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()
