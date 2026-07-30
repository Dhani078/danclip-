from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./clipper.db"
    GEMINI_API_KEY: str = ""
    STORAGE_DIR: str = "./storage"
    TIKTOK_CLIENT_KEY: str = "sbawv5w4g121qq6vxm"
    TIKTOK_CLIENT_SECRET: str = "SPb7gADqQt9BAhST4ywO7tIlC0e60COc"
    TIKTOK_ACCESS_TOKEN: str = ""
    TIKTOK_REFRESH_TOKEN: str = ""
    DEFAULT_WEBHOOK_URL: str = "tg:8870492783:AAFLR7nuio7faUpiuwLhLeQK4VY1EV1q9_o:1224442718"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

# Ensure storage directories exist
os.makedirs(os.path.join(settings.STORAGE_DIR, "temp"), exist_ok=True)
os.makedirs(os.path.join(settings.STORAGE_DIR, "exports"), exist_ok=True)
