import os

os.environ.setdefault("OTEL_ENABLED", "false")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("GROQ_API_KEY", "test-key")

import pytest
from app.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
