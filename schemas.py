from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional
from datetime import datetime
from models import JobStatus

class ClipRequest(BaseModel):
    youtube_urls: List[str]  # Allows batch processing of multiple URLs
    aspect_ratio: str = "9:16"
    subtitle_color: str = "&H00FFFF"
    subtitle_size: int = 90
    subtitle_opacity: int = 100
    subtitle_preset: str = "hormozi"
    subtitle_position: str = "bottom"
    target_language: str = "id"  # 'id', 'en', 'es', 'ja', 'ar'
    crop_style: str = "center_crop"
    enable_subtitles: bool = False
    custom_prompt: Optional[str] = ""
    clip_count: int = 3
    auto_reframe: bool = False
    word_karaoke: bool = False
    bgm_ducking: bool = False
    layout_mode: str = "auto"
    watermark_position: Optional[str] = "top_right"
    watermark_path: Optional[str] = ""
    enable_sfx: Optional[bool] = True
    webhook_url: Optional[str] = ""
    gemini_api_key: Optional[str] = ""
    target_keyword: Optional[str] = ""
    target_start_time: Optional[str] = ""
    target_end_time: Optional[str] = ""

class ClipResponse(BaseModel):
    job_id: str
    job_ids: Optional[List[str]] = []
    status: JobStatus

class VideoJobDetail(BaseModel):
    id: str
    youtube_url: str
    video_title: Optional[str]
    duration_seconds: Optional[int]
    status: JobStatus
    progress_percentage: int
    current_step_message: str
    clips_json: Optional[str]
    output_video_path: Optional[str]
    error_log: Optional[str]
    aspect_ratio: Optional[str]
    subtitle_color: Optional[str]
    subtitle_size: Optional[int]
    subtitle_opacity: Optional[int]
    subtitle_preset: Optional[str]
    subtitle_position: Optional[str]
    target_language: Optional[str]
    crop_style: Optional[str]
    enable_subtitles: Optional[bool]
    custom_prompt: Optional[str]
    clip_count: Optional[int]
    auto_reframe: Optional[bool]
    word_karaoke: Optional[bool]
    bgm_ducking: Optional[bool]
    layout_mode: Optional[str]
    watermark_path: Optional[str]
    watermark_position: Optional[str]
    custom_font_path: Optional[str]
    enable_sfx: Optional[bool]
    webhook_url: Optional[str]
    gemini_api_key: Optional[str]
    target_keyword: Optional[str]
    target_start_time: Optional[str]
    target_end_time: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}

class ClipAnalysis(BaseModel):
    id: str = Field(description="Unique ID for this clip, e.g. clip_1")
    start_time: str = Field(description="Start time in MM:SS")
    end_time: str = Field(description="End time in MM:SS")
    viral_score: int = Field(description="Score from 1-100")
    viral_reasoning: str = Field(default="", description="Detailed 2-3 sentence AI analysis breakdown explaining why this clip is viral (e.g., retention hooks, provocative question, high emotional value)")
    hook_title: str = Field(default="", description="Short 3-6 word viral header title to be displayed on top of the clip, e.g. RAHASIA MOBIL LISTRIK CHINA! 🔥")
    caption: str = Field(description="Engaging caption for TikTok/Reels")
    hashtags: List[str] = Field(description="List of exactly 5 relevant hashtags (min 5, max 5)")
    tiktok_titles: List[str] = Field(default=[], description="3 unique viral title variations for TikTok")
    reels_titles: List[str] = Field(default=[], description="3 aesthetic title variations for Instagram Reels")
    shorts_titles: List[str] = Field(default=[], description="3 punchy title variations for YouTube Shorts")
    tiktok_hashtags: List[str] = Field(default=[], description="List of exactly 5 platform-tailored TikTok hashtags (min 5, max 5)")
    reels_hashtags: List[str] = Field(default=[], description="List of exactly 5 platform-tailored Instagram Reels hashtags (min 5, max 5)")
    shorts_hashtags: List[str] = Field(default=[], description="List of exactly 5 platform-tailored YouTube Shorts hashtags (min 5, max 5)")
    tiktok_caption: str = Field(default="", description="Platform-tailored TikTok caption with viral hook, emojis, and trending hashtags e.g. #fyp #foryoupage")
    reels_caption: str = Field(default="", description="Platform-tailored Instagram Reels caption with aesthetic storytelling tone and hashtags e.g. #reels #explore")
    shorts_caption: str = Field(default="", description="Platform-tailored YouTube Shorts title caption with punchy tag format and hashtags e.g. #shorts #trending")
class GeminiAnalysisSchema(BaseModel):
    clips: List[ClipAnalysis] = Field(description="List of extracted viral clips")
