import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings


def get_db_url() -> str:
    return settings.DATABASE_URL


def ensure_db_dir(url: str):
    if url.startswith("sqlite:///"):
        db_path = url.replace("sqlite:///", "")
        if db_path and db_path != ":memory:":
            dirname = os.path.dirname(db_path)
            if dirname:
                os.makedirs(dirname, exist_ok=True)


db_url = get_db_url()
ensure_db_dir(db_url)

connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
engine = create_engine(db_url, connect_args=connect_args, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
