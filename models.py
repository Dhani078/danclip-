from sqlalchemy import Column, String, Integer, Text, Boolean, Enum as SQLEnum, DateTime, func, ForeignKey
from sqlalchemy.orm import relationship
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
    CANCELLED = "CANCELLED"

class VideoJob(Base):
    __tablename__ = "video_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    youtube_url = Column(String, nullable=False, index=True)
    video_title = Column(String, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    status = Column(SQLEnum(JobStatus), default=JobStatus.QUEUED, index=True)
    progress_percentage = Column(Integer, default=0)
    current_step_message = Column(String, default='Enqueued')
    
    @property
    def clips_json(self):
        import json
        if not self.clips:
            return ""
        
        def format_time(seconds):
            if seconds is None: return "00:00"
            if isinstance(seconds, str):
                s_str = seconds.strip()
                if ":" in s_str:
                    return s_str
                try:
                    seconds = float(s_str)
                except ValueError:
                    return "00:00"
            try:
                sec_int = int(float(seconds))
                m, s = divmod(sec_int, 60)
                if m >= 60:
                    h, m = divmod(m, 60)
                    return f"{h:02d}:{m:02d}:{s:02d}"
                return f"{m:02d}:{s:02d}"
            except Exception:
                return "00:00"

        c_list = []
        for c in self.clips:
            try:
                hashtags = json.loads(c.hashtags_json) if c.hashtags_json else []
            except Exception:
                hashtags = []
                
            c_list.append({
                "id": c.id,
                "start": c.start_sec,
                "end": c.end_sec,
                "start_time": format_time(c.start_sec),
                "end_time": format_time(c.end_sec),
                "viral_score": c.viral_score,
                "viral_reasoning": c.viral_reasoning,
                "hook_title": c.hook_title,
                "caption": c.caption,
                "hashtags": hashtags,
                "output_path": c.output_path,
                "thumbnail_path": c.thumbnail_path,
                "status": c.status,
                "error": c.error
            })
        return json.dumps(c_list)
    output_video_path = Column(String, nullable=True)
    error_log = Column(Text, nullable=True)
    
    # Advanced Settings
    aspect_ratio = Column(String(20), default="9:16")
    subtitle_color = Column(String(20), default="&H00FFFF")
    subtitle_size = Column(Integer, default=90)
    subtitle_opacity = Column(Integer, default=100)
    subtitle_preset = Column(String(50), default="hormozi")
    subtitle_position = Column(String(20), default="bottom")
    subtitle_margin_v = Column(Integer, nullable=True)
    target_language = Column(String(10), default="id")
    crop_style = Column(String(20), default="center_crop")
    enable_subtitles = Column(Boolean, default=False)
    
    # New Opus-Clip Pro Features
    custom_prompt = Column(Text, nullable=True)
    clip_count = Column(Integer, default=3)
    auto_reframe = Column(Boolean, default=False)
    word_karaoke = Column(Boolean, default=False)
    bgm_ducking = Column(Boolean, default=False)
    # Watermark, SFX, & Custom Font
    watermark_path = Column(String(255), nullable=True)
    watermark_position = Column(String(20), default="top_right")
    custom_font_path = Column(String(255), nullable=True)
    enable_sfx = Column(Boolean, default=True)
    webhook_url = Column(String, nullable=True)
    gemini_api_key = Column(String, nullable=True)
    target_keyword = Column(String, nullable=True)
    target_start_time = Column(String, nullable=True)
    target_end_time = Column(String, nullable=True)
    layout_mode = Column(String(20), default="auto")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    clips = relationship("Clip", back_populates="job", cascade="all, delete-orphan", order_by="Clip.clip_index")

class Clip(Base):
    __tablename__ = "clips"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("video_jobs.id"), index=True)
    clip_index = Column(Integer, default=0)
    start_sec = Column(Integer, nullable=True)
    end_sec = Column(Integer, nullable=True)
    viral_score = Column(Integer, nullable=True)
    viral_reasoning = Column(Text, nullable=True)
    hook_title = Column(String, nullable=True)
    caption = Column(Text, nullable=True)
    hashtags_json = Column(Text, nullable=True)
    platform_meta_json = Column(Text, nullable=True)
    output_path = Column(String, nullable=True)
    thumbnail_path = Column(String, nullable=True)
    status = Column(String(20), default="PENDING")
    error = Column(Text, nullable=True)
    
    job = relationship("VideoJob", back_populates="clips")

class TikTokAuth(Base):
    __tablename__ = "tiktok_auth"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    open_id = Column(String, nullable=False)
    expires_at = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())
