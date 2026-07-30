from sqlalchemy import Column, String, Integer, Text, Boolean, Enum as SQLEnum, DateTime, func
from database import Base
import enum
import uuid

class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    DOWNLOADING = "DOWNLOADING"
    ANALYZING = "ANALYZING"
    EDITING = "EDITING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class VideoJob(Base):
    __tablename__ = "video_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    youtube_url = Column(String, nullable=False, index=True)
    video_title = Column(String, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    status = Column(SQLEnum(JobStatus), default=JobStatus.QUEUED)
    progress_percentage = Column(Integer, default=0)
    current_step_message = Column(String, default='Enqueued')
    
    # Store multiple clips from Gemini as JSON string
    clips_json = Column(Text, nullable=True) 
    
    output_video_path = Column(String, nullable=True)
    error_log = Column(Text, nullable=True)
    
    # Advanced Settings
    aspect_ratio = Column(String(20), default="9:16")
    subtitle_color = Column(String(20), default="&H00FFFF")
    subtitle_size = Column(Integer, default=90)
    crop_style = Column(String(20), default="center_crop")
    
    # New Opus-Clip Pro Features
    custom_prompt = Column(Text, nullable=True)
    clip_count = Column(Integer, default=3)
    auto_reframe = Column(Boolean, default=False)
    word_karaoke = Column(Boolean, default=False)
    bgm_ducking = Column(Boolean, default=False)
    layout_mode = Column(String(20), default="auto")
    webhook_url = Column(String, nullable=True)
    gemini_api_key = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
