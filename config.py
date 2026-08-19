from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./clipper.db"
    GEMINI_API_KEY: str = ""
    STORAGE_DIR: str = "./storage"
    TIKTOK_CLIENT_KEY: str = ""
    TIKTOK_CLIENT_SECRET: str = ""
    TIKTOK_ACCESS_TOKEN: str = ""
    TIKTOK_REFRESH_TOKEN: str = ""
    DEFAULT_WEBHOOK_URL: str = ""
    MAX_SOURCE_HEIGHT: int = 1080
    APP_PASSWORD: str = ""
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

# Ensure storage directories exist
os.makedirs(os.path.join(settings.STORAGE_DIR, "temp"), exist_ok=True)
os.makedirs(os.path.join(settings.STORAGE_DIR, "exports"), exist_ok=True)
os.makedirs(os.path.join(settings.STORAGE_DIR, "sources"), exist_ok=True)
