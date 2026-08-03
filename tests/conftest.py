import os
import pytest
from fastapi.testclient import TestClient

# Ensure test DB is set before importing app
os.environ["DATABASE_URL"] = "sqlite:///./data/test_kai.db"

from app.main import create_app
from app.db.base import Base
from app.db.session import engine, SessionLocal


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./data/test_kai.db"):
        try:
            os.remove("./data/test_kai.db")
        except OSError:
            pass


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
