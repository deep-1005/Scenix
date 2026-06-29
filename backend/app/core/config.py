from pydantic_settings import BaseSettings  # type: ignore

class Settings(BaseSettings):
    database_url: str = "sqlite:///./forensic.db"
    redis_url: str = "redis://localhost:6379/0"
    storage_uploads: str = "storage/uploads"
    storage_outputs: str = "storage/outputs"
    colmap_use_gpu: bool = False

    class Config:
        env_file = ".env"

settings = Settings()