"""Base PostgreSQL de test dédiée (recréée à chaque session, migrations Alembic appliquées)."""
import os
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import text

TEST_DB = os.environ.get("TEST_DATABASE_NAME", "medisight_test")
BASE = os.environ.get("TEST_DATABASE_BASE", "postgresql+psycopg://medisight:medisight@localhost:5432")
os.environ["DATABASE_URL"] = f"{BASE}/{TEST_DB}"
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def engine():
    with psycopg.connect(BASE.replace("+psycopg", "") + "/postgres", autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {TEST_DB}")
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    command.upgrade(cfg, "head")
    from app.db.session import get_engine
    yield get_engine()


@pytest.fixture
def db(engine):
    import app.models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_sessionmaker
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(t.name for t in Base.metadata.sorted_tables) + " RESTART IDENTITY CASCADE"))
    session = get_sessionmaker()()
    yield session
    session.close()


@pytest.fixture
def seeded(db):
    from app.ingestion.seed import seed_all
    seed_all(db, ROOT / "data")
    return db
