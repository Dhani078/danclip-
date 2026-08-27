from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy import event
from config import settings

engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=False,
    connect_args={"timeout": 30}
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def init_db():
    import asyncio
    import sqlite3
    from alembic.config import Config
    from alembic import command
    
    def run_migrations():
        alembic_cfg = Config("alembic.ini")
        try:
            command.upgrade(alembic_cfg, "head")
        except Exception:
            pass
            
        # Fallback safe auto-column check for SQLite
        try:
            db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(video_jobs)")
                cols = [row[1] for row in cursor.fetchall()]
                if cols and "clip_mode" not in cols:
                    cursor.execute("ALTER TABLE video_jobs ADD COLUMN clip_mode VARCHAR DEFAULT 'single'")
                    conn.commit()
                conn.close()
        except Exception:
            pass
            
    await asyncio.to_thread(run_migrations)
