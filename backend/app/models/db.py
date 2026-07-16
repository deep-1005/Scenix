from sqlalchemy import create_engine, Column, String, DateTime, Integer, Text  # type: ignore
from sqlalchemy.orm import declarative_base, sessionmaker  # type: ignore
from datetime import datetime
import uuid
from app.core.config import settings

# SQLite needs check_same_thread=False; the connect_args are ignored by other DBs
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Job(Base):
    __tablename__ = "jobs"

    id          = Column(String,   primary_key=True, default=lambda: str(uuid.uuid4()))
    status      = Column(String,   default="created")   # created|queued|running|done|failed
    stage       = Column(String,   default="")
    progress    = Column(Integer,  default=0)
    scene_name  = Column(String,   default="")
    upload_path = Column(String,   default="")
    output_path = Column(String,   default="")
    summary     = Column(Text,     default="{}")
    error       = Column(Text,     default="")
    log_tail    = Column(Text,     default="")          # last line of FastGS output
    task_id     = Column(String,   default="")           # Celery task id, used to revoke on cancel
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db():
    Base.metadata.create_all(engine)