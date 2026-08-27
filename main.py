from fastapi import FastAPI, BackgroundTasks, Depends, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from pydantic import BaseModel
import asyncio
import os
import sys
import shutil
from datetime import datetime, timedelta
import hashlib
import yt_dlp

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
import traceback
import json
import re
import subprocess
from typing import List, Optional

import httpx
import uuid
import io
from pathlib import Path
from PIL import Image, UnidentifiedImageError

# Job queue semaphore: only 1 job at a time to prevent VRAM/RAM overflow
_job_semaphore = asyncio.Semaphore(1)

from config import settings
from database import init_db, get_db, AsyncSessionLocal
from models import VideoJob, JobStatus
from schemas import ClipRequest, ClipResponse, VideoJobDetail
from services.gemini import analyze_video
from services.ffmpeg import render_viral_clip
from services.whisper_stt import generate_whisper_srt
from services.thumbnail import generate_viral_thumbnail
from services.notifications import send_webhook_notification
from services.tiktok_publisher import publish_video_to_tiktok

from contextlib import asynccontextmanager

EXPORTS_DIR = Path(settings.STORAGE_DIR, "exports").resolve()

def validate_export_path(raw: str) -> Path:
    p = (EXPORTS_DIR / Path(raw).name).resolve()
    if not p.is_relative_to(EXPORTS_DIR):
        raise HTTPException(400, "Path tidak valid")
    if p.suffix.lower() != ".mp4":
        raise HTTPException(400, "Hanya file .mp4 yang diizinkan")
    if not p.is_file():
        raise HTTPException(404, "File tidak ditemukan")
    return p

def cleanup_temp_storage():
    """Cleans up orphan audio and subtitle temporary files older than 6 hours."""
    temp_dir = os.path.join(settings.STORAGE_DIR, "temp")
    if not os.path.exists(temp_dir):
        return
    now = datetime.now()
    for fname in os.listdir(temp_dir):
        fpath = os.path.join(temp_dir, fname)
        try:
            if os.path.isfile(fpath):
                file_time = datetime.fromtimestamp(os.path.getmtime(fpath))
                if now - file_time > timedelta(hours=6):
                    os.remove(fpath)
        except Exception:
            pass

def link_or_copy(src: str, dst: str) -> None:
    if os.path.exists(dst):
        return
    try:
        os.link(src, dst)
    except (OSError, AttributeError):
        shutil.copy2(src, dst)


async def download_youtube_video(url: str, dest_path: str) -> tuple[str, int]:
    # Extract info first
    cmd_info = [sys.executable, "-m", "yt_dlp", "--dump-json", url]
    proc_res = await run_subprocess_async(cmd_info)
    stdout, _ = await proc_res.communicate()
    
    title = "Unknown"
    duration = 0
    try:
        info = json.loads(stdout.decode())
        title = info.get("title", "Unknown")
        duration = info.get("duration", 0)
    except (json.JSONDecodeError, KeyError, TypeError, Exception):
        pass
        
    max_height = settings.MAX_SOURCE_HEIGHT
    
    ydl_opts = [
        sys.executable, "-m", "yt_dlp",
        "-f", f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={max_height}][ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", dest_path,
        url
    ]
    
    proc2 = await run_subprocess_async(ydl_opts)
    if proc2.returncode != 0:
        # Fallback 1: Edge
        ydl_opts_edge = ydl_opts.copy()
        ydl_opts_edge.insert(3, "--cookies-from-browser")
        ydl_opts_edge.insert(4, "edge")
        proc3 = await run_subprocess_async(ydl_opts_edge)
        if proc3.returncode != 0:
            # Fallback 2: Chrome
            ydl_opts_chrome = ydl_opts.copy()
            ydl_opts_chrome.insert(3, "--cookies-from-browser")
            ydl_opts_chrome.insert(4, "chrome")
            proc4 = await run_subprocess_async(ydl_opts_chrome)
            if proc4.returncode != 0:
                raise Exception("Gagal mengunduh video setelah semua metode dicoba.")
                
    return title, duration


async def ensure_source_video(job) -> str:
    """Mengembalikan path video sumber yang PASTI ada di disk."""
    temp_dir = os.path.join(settings.STORAGE_DIR, "temp")
    src_dir = os.path.join(settings.STORAGE_DIR, "sources")
    os.makedirs(src_dir, exist_ok=True)

    if (job.youtube_url or "").startswith("local://"):
        p = os.path.join(src_dir, f"{job.id}.mp4")
        if os.path.exists(p):
            return p
        raise Exception("File sumber upload lokal sudah tidak ada. Silakan unggah ulang video.")

    work = os.path.join(temp_dir, f"{job.id}.mp4")
    if os.path.exists(work):
        return work

    url_clean = (job.youtube_url or "").strip()
    url_hash = hashlib.md5(url_clean.encode("utf-8")).hexdigest()[:16]
    cached = os.path.join(temp_dir, f"cache_{url_hash}.mp4")
    if os.path.exists(cached):
        mtime = datetime.fromtimestamp(os.path.getmtime(cached))
        if datetime.now() - mtime < timedelta(hours=6):
            link_or_copy(cached, work)
            return work

    title, duration = await download_youtube_video(job.youtube_url, cached)
    link_or_copy(cached, work)
    return work

async def lifespan(app: FastAPI):
    await init_db()
    
    # Cleanup Zombie Jobs
    from sqlalchemy import update
    from database import AsyncSessionLocal
    from models import VideoJob, JobStatus
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(VideoJob)
            .where(VideoJob.status.in_([JobStatus.QUEUED, JobStatus.DOWNLOADING, JobStatus.ANALYZING, JobStatus.EDITING]))
            .values(status=JobStatus.FAILED, error_log='Server dimatikan saat job berjalan')
        )
        await session.commit()
        
    cleanup_temp_storage()
    from services.notifications import start_telegram_bot_listener
    tg_token = ""
    target_wh = (settings.DEFAULT_WEBHOOK_URL or "").strip()
    if target_wh.startswith("tg:"):
        parts = target_wh.split(":")
        if len(parts) >= 3:
            tg_token = f"{parts[1]}:{parts[2]}"
    elif "/bot" in target_wh:
        try:
            tg_token = target_wh.split("/bot")[1].split("/")[0]
        except Exception:
            pass
    listener_task = asyncio.create_task(start_telegram_bot_listener(tg_token))
    yield
    listener_task.cancel()

active_tasks = {}
active_subprocesses = {}

class SubprocessResult:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        
    async def communicate(self):
        return self.stdout, self.stderr

async def run_subprocess_async(cmd, job_id=None, cwd=None):
    """
    Cross-platform safe subprocess execution for Windows & Linux.
    Works on Uvicorn with WindowsSelectorEventLoopPolicy without throwing NotImplementedError.
    """
    import subprocess
    
    def _worker():
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
        if job_id:
            active_subprocesses[job_id] = p
        stdout, stderr = p.communicate()
        if job_id:
            active_subprocesses.pop(job_id, None)
        return SubprocessResult(p.returncode, stdout, stderr)

    return await asyncio.to_thread(_worker)

async def run_with_backoff(func, max_retries=3, backoff_factor=2):
    import asyncio
    retries = 0
    while True:
        try:
            return await func()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if retries >= max_retries:
                raise e
            msg = str(e).lower()
            if any(term in msg for term in ["429", "500", "502", "503", "504", "timeout", "network", "unavailable", "connection", "rate limit"]):
                print(f"[Retry] Transient error. Retrying in {backoff_factor ** (retries + 1)}s... Error: {msg}")
                await asyncio.sleep(backoff_factor ** (retries + 1))
                retries += 1
            else:
                raise e

app = FastAPI(title="AI Auto-Clipper API", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"[Global Exception] {traceback.format_exc()}")
    return HTMLResponse(content="<pre>Internal Server Error</pre>", status_code=500)

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return HTMLResponse(content="", status_code=204)

os.makedirs(os.path.join(settings.STORAGE_DIR, "exports"), exist_ok=True)
app.mount("/exports", StaticFiles(directory=os.path.join(settings.STORAGE_DIR, "exports")), name="exports")

async def process_video_pipeline(job_id: str):
    import asyncio
    active_tasks[job_id] = asyncio.current_task()

    async with _job_semaphore:
        from database import AsyncSessionLocal
        session = AsyncSessionLocal()
        try:
            # Step 1: DOWNLOADING
            job = await session.get(VideoJob, job_id)
            if not job:
                return
                
            job.status = JobStatus.DOWNLOADING
            job.progress_percentage = 15
            job.current_step_message = "Downloading video via yt-dlp..."
            await session.commit()
            
            temp_dir = os.path.join(settings.STORAGE_DIR, "temp")
            raw_video_path = os.path.join(temp_dir, f"{job_id}.mp4")
            
            if os.path.exists(raw_video_path):
                print(f"[Pipeline] Local video file already uploaded: {raw_video_path}. Skipping yt-dlp download.")
                title = job.video_title or 'Local Video'
                duration = job.duration_seconds or 0
            else:
                # URL-based 6-hour Local Caching Mechanism
                url_clean = (job.youtube_url or "").strip()
                url_hash = hashlib.md5(url_clean.encode('utf-8')).hexdigest()[:16] if url_clean else job_id
                cached_video_path = os.path.join(temp_dir, f"cache_{url_hash}.mp4")
                cached_meta_path = os.path.join(temp_dir, f"cache_{url_hash}.json")
                
                use_cache = False
                if os.path.exists(cached_video_path):
                    mtime = datetime.fromtimestamp(os.path.getmtime(cached_video_path))
                    if datetime.now() - mtime < timedelta(hours=6):
                        use_cache = True
                        
                if use_cache:
                    print(f"[yt-dlp Cache] Reusing local cached video for URL ({url_hash}): {cached_video_path} (Skipping yt-dlp download)")
                    link_or_copy(cached_video_path, raw_video_path)
                    title = job.video_title or 'Cached Video'
                    duration = job.duration_seconds or 0
                    if os.path.exists(cached_meta_path):
                        try:
                            with open(cached_meta_path, "r", encoding="utf-8") as f:
                                meta_data = json.load(f)
                                title = meta_data.get("title", title)
                                duration = meta_data.get("duration", duration)
                        except Exception:
                            pass
                else:
                    cmd = [
                        "python", "-m", "yt_dlp",
                        "-f", f"bestvideo[height<={settings.MAX_SOURCE_HEIGHT}][ext=mp4]+bestaudio[ext=m4a]/best[height<={settings.MAX_SOURCE_HEIGHT}][ext=mp4]/best",
                        "--merge-output-format", "mp4",
                        "-o", cached_video_path,
                        "--quiet",
                        "--no-warnings",
                        "--dump-json",
                        "--no-simulate",
                        "--retries", "10",
                        "--concurrent-fragments", "5",
                        "--js-runtimes", "node"
                    ]
                    
                    cookies_txt = os.path.abspath("cookies.txt")
                    if os.path.exists(cookies_txt):
                        cmd.extend(["--cookies", cookies_txt])
                        
                    cmd.append(job.youtube_url)
                    
                    process = None
                    async def _run_ytdlp():
                        proc_res = await run_subprocess_async(cmd, job_id=job_id)
                        stdout, stderr = await proc_res.communicate()
                        
                        if proc_res.returncode != 0:
                            error_msg = stderr.decode('utf-8', errors='ignore').strip()
                            if "bot" in error_msg.lower() or "sign in" in error_msg.lower():
                                print("[yt-dlp] Bot detection triggered. Retrying with Chrome browser cookies...")
                                cookie_cmd = list(cmd)
                                cookie_cmd.extend(["--cookies-from-browser", "chrome"])
                                proc_res = await run_subprocess_async(cookie_cmd, job_id=job_id)
                                stdout, stderr = await proc_res.communicate()
                                if proc_res.returncode != 0:
                                    cookie_cmd2 = list(cmd)
                                    cookie_cmd2.extend(["--cookies-from-browser", "edge"])
                                    proc_res = await run_subprocess_async(cookie_cmd2, job_id=job_id)
                                    stdout, stderr = await proc_res.communicate()
                            
                            if proc_res.returncode != 0:
                                error_msg = stderr.decode('utf-8', errors='ignore').strip()
                                raise Exception(f"Video unavailable or invalid URL (yt-dlp failed): {error_msg}")
                        return stdout

                    stdout = await run_with_backoff(_run_ytdlp)
                        
                    try:
                        info = json.loads(stdout.decode('utf-8', errors='ignore'))
                        title = info.get('title', 'Unknown Title')
                        duration = info.get('duration', 0)
                        with open(cached_meta_path, "w", encoding="utf-8") as f:
                            json.dump({"title": title, "duration": duration}, f)
                    except Exception:
                        title = 'Downloaded Video'
                        duration = 0
                    
                    # Copy cached file to job raw_video_path
                    link_or_copy(cached_video_path, raw_video_path)
                
            job.video_title = title
            job.duration_seconds = duration
            await session.commit()

            # Step 2: Transcribe Full Video with Whisper
            job.status = JobStatus.ANALYZING
            job.progress_percentage = 40
            job.current_step_message = "Transcribing full video with Whisper Turbo (frame-accurate)..."
            await session.commit()
            
            whisper_wav = os.path.join(temp_dir, f"{job_id}_full_whisper.wav")
            from services.ffmpeg import FFMPEG_CMD
            audio_cmd = [FFMPEG_CMD, "-y", "-i", raw_video_path, "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", whisper_wav]
            audio_res = await run_subprocess_async(audio_cmd, job_id=job_id)
            if audio_res.returncode != 0:
                raise Exception("Failed to extract full audio for Whisper.")
                
            from services.whisper_stt import transcribe_audio_to_words, generate_ass_from_words, unload_whisper_model, format_ass_time
            
            # Transcription Caching Mechanism
            url_clean_whisper = (job.youtube_url or "").strip()
            whisper_cache_key = hashlib.md5(url_clean_whisper.encode('utf-8')).hexdigest()[:16] if url_clean_whisper else job_id
            whisper_cache_path = os.path.join(temp_dir, f"whisper_cache_{whisper_cache_key}.json")
            
            try:
                full_words = None
                if os.path.exists(whisper_cache_path):
                    print(f"[Whisper Cache] Reusing local cached transcription for ({whisper_cache_key})")
                    try:
                        with open(whisper_cache_path, "r", encoding="utf-8") as f:
                            full_words = json.load(f)
                    except Exception:
                        pass
                        
                if not full_words:
                    full_words = await asyncio.to_thread(
                        transcribe_audio_to_words, 
                        whisper_wav, 
                        "auto", 
                        getattr(job, "target_language", "id")
                    )
                    try:
                        with open(whisper_cache_path, "w", encoding="utf-8") as f:
                            json.dump(full_words, f)
                    except Exception:
                        pass
            except Exception as e:
                raise Exception(f"Whisper Transcription Failed: {e}")
            finally:
                if os.path.exists(whisper_wav):
                    os.remove(whisper_wav)
                await asyncio.to_thread(unload_whisper_model)

            # Step 2.5: ANALYZING (Hybrid: Audio or Transcript Chunking)
            job.progress_percentage = 50
            
            if getattr(job, "duration_seconds", 0) > 1200: # 20 minutes
                job.current_step_message = "Video > 20 mins. Using Transcript Chunking for AI analysis..."
                await session.commit()
                
                transcript_lines = []
                current_chunk = []
                current_start = 0
                for w in full_words:
                    if not current_chunk:
                        current_start = float(w['start'])
                    current_chunk.append(w['word'])
                    if w['end'] - current_start > 10 or w['word'].strip().endswith(('.', '?', '!')):
                        ts = format_ass_time(current_start).split('.')[0] # HH:MM:SS
                        transcript_lines.append(f"[{ts}] {''.join(current_chunk).strip()}")
                        current_chunk = []
                transcript_text = "\n".join(transcript_lines)
                
                from services.gemini import analyze_transcript_chunks
                analysis = await run_with_backoff(lambda: analyze_transcript_chunks(
                    transcript_text, 
                    job.custom_prompt, 
                    job.clip_count, 
                    custom_api_key=getattr(job, "gemini_api_key", "") or "",
                    clip_mode=getattr(job, "clip_mode", "single") or "single"
                ))
            else:
                job.current_step_message = "Extracting audio for AI analysis (saving tokens)..."
                await session.commit()
                
                audio_path = os.path.join(temp_dir, f"{job_id}.mp3")
                from services.ffmpeg import FFMPEG_CMD
                audio_cmd = [FFMPEG_CMD, "-y", "-i", raw_video_path, "-vn", "-c:a", "libmp3lame", "-q:a", "5", audio_path]
                audio_res = await run_subprocess_async(audio_cmd, job_id=job_id)
                if audio_res.returncode != 0:
                    raise Exception("Failed to extract audio for analysis.")
                    
                job.current_step_message = "Analyzing viral moments with Gemini Auto-Fallback Engine..."
                await session.commit()
                
                from services.gemini import analyze_video
                analysis = await run_with_backoff(lambda: analyze_video(
                    audio_path, 
                    job.custom_prompt, 
                    job.clip_count, 
                    custom_api_key=getattr(job, "gemini_api_key", "") or "",
                    target_keyword=getattr(job, "target_keyword", "") or "",
                    target_start_time=getattr(job, "target_start_time", "") or "",
                    target_end_time=getattr(job, "target_end_time", "") or "",
                    clip_mode=getattr(job, "clip_mode", "single") or "single"
                ))
                
                if os.path.exists(audio_path):
                    os.remove(audio_path)

            # Step 3: EDITING
            job.status = JobStatus.EDITING
            job.progress_percentage = 75
            
            if not analysis or not getattr(analysis, 'clips', None) or len(analysis.clips) == 0:
                raise Exception("AI failed to extract any viral clips. Please check the API quota or prompt instructions.")
            
            clips_data = []
            output_paths = []
            
            def parse_time(ts):
                if isinstance(ts, (int, float)): return float(ts)
                ts_str = str(ts).strip()
                parts = ts_str.split(':')
                try:
                    if len(parts) == 2: return float(parts[0]) * 60.0 + float(parts[1])
                    elif len(parts) == 3: return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
                    return float(ts_str)
                except Exception:
                    return 0.0
                
            for i, clip in enumerate(analysis.clips):
                job.current_step_message = f"Generating ASS and UI metadata for clip {i+1}/{len(analysis.clips)}..."
                job.progress_percentage = 75 + int((i / len(analysis.clips)) * 10)
                await session.commit()
                
                hook_title_text = getattr(clip, "hook_title", "")
                
                start_sec = float(parse_time(clip.start_time))
                end_sec = float(parse_time(clip.end_time))
                
                clip_segments = getattr(clip, "segments", None)
                seg_list = None
                if clip_segments and hasattr(clip_segments, '__iter__'):
                    seg_list = [s.model_dump() if hasattr(s, 'model_dump') else (s.dict() if hasattr(s, 'dict') else s) for s in clip_segments]

                whisper_srt = generate_ass_from_words(
                    full_words, start_sec, end_sec,
                    sub_size=job.subtitle_size, sub_color=job.subtitle_color, word_karaoke=job.word_karaoke,
                    hook_title=hook_title_text, subtitle_preset=getattr(job, "subtitle_preset", "hormozi"),
                    subtitle_position=getattr(job, "subtitle_position", "bottom"),
                    sub_opacity=getattr(job, "subtitle_opacity", 100),
                    segments=seg_list
                )
                
                cover_export_path = os.path.join(settings.STORAGE_DIR, "exports", f"{job_id}_{clip.id}_cover.jpg")
                
                clips_data.append({
                    "id": clip.id,
                    "job_id": job_id,
                    "start_time": clip.start_time,
                    "end_time": clip.end_time,
                    "viral_score": clip.viral_score,
                    "viral_reasoning": getattr(clip, "viral_reasoning", ""),
                    "hook_title": hook_title_text,
                    "caption": clip.caption,
                    "hashtags": clip.hashtags,
                    "tiktok_titles": getattr(clip, "tiktok_titles", []),
                    "reels_titles": getattr(clip, "reels_titles", []),
                    "shorts_titles": getattr(clip, "shorts_titles", []),
                    "tiktok_hashtags": getattr(clip, "tiktok_hashtags", []),
                    "reels_hashtags": getattr(clip, "reels_hashtags", []),
                    "shorts_hashtags": getattr(clip, "shorts_hashtags", []),
                    "tiktok_caption": getattr(clip, "tiktok_caption", clip.caption),
                    "reels_caption": getattr(clip, "reels_caption", clip.caption),
                    "shorts_caption": getattr(clip, "shorts_caption", clip.caption),
                    "srt_subtitles": whisper_srt,
                    "cover_url": f"/exports/{job_id}_{clip.id}_cover.jpg"
                })
                
                job.current_step_message = f"Rendering clip {i+1}/{len(analysis.clips)} with FFmpeg..."
                await session.commit()
                
                subtitle_path = None
                if whisper_srt:
                    subtitle_path = os.path.join(temp_dir, f"{job_id}_{clip.id}.ass")
                    with open(subtitle_path, "w", encoding="utf-8") as f:
                        f.write(whisper_srt)
                
                export_path = os.path.join(settings.STORAGE_DIR, "exports", f"{job_id}_{clip.id}.mp4")
                
                job_settings = {
                    "aspect_ratio": job.aspect_ratio,
                    "subtitle_color": job.subtitle_color,
                    "subtitle_size": job.subtitle_size,
                    "crop_style": job.crop_style,
                    "auto_reframe": job.auto_reframe,
                    "word_karaoke": job.word_karaoke,
                    "bgm_ducking": job.bgm_ducking,
                    "watermark_path": getattr(job, "watermark_path", None),
                    "watermark_position": getattr(job, "watermark_position", "top_right"),
                    "custom_font_path": getattr(job, "custom_font_path", None),
                    "enable_sfx": getattr(job, "enable_sfx", True),
                    "layout_mode": getattr(job, "layout_mode", "auto"),
                    "layout_type": getattr(clip, "layout_type", "single"),
                    "speaker_focus": getattr(clip, "speaker_focus", "center"),
                    "has_broll": getattr(clip, "has_broll", False),
                    "segments": seg_list
                }
                await render_viral_clip(raw_video_path, export_path, clip.start_time, clip.end_time, subtitle_path, job_settings, burn_subtitles=getattr(job, "enable_subtitles", False))
                
                # Generate high-impact viral cover image (.jpg) - DISABLED BY USER REQUEST
                # await asyncio.to_thread(generate_viral_thumbnail, export_path, cover_export_path, hook_title_text, clip.viral_score)
                
                # Generate 3 AI Thumbnail Variants - DISABLED BY USER REQUEST
                # from services.ffmpeg import generate_viral_thumbnails
                # thumb_vars = await generate_viral_thumbnails(raw_video_path, clip.start_time, clip.end_time, hook_title_text, export_path)
                # thumb_urls = [f"/exports/{os.path.basename(p)}" for p in thumb_vars]
                clips_data[-1]["thumbnail_variants"] = []
                
                output_paths.append(f"/exports/{job_id}_{clip.id}.mp4")
                
                if subtitle_path and os.path.exists(subtitle_path):
                    os.remove(subtitle_path)
                    
            from models import Clip
            clip_objs = []
            for idx, c in enumerate(clips_data):
                clip_objs.append(Clip(
                    job_id=job.id,
                    clip_index=idx,
                    start_sec=int(parse_time(c.get('start_time', 0))),
                    end_sec=int(parse_time(c.get('end_time', 0))),
                    viral_score=int(c.get('viral_score', 0)),
                    viral_reasoning=c.get('viral_reasoning', ''),
                    hook_title=c.get('hook_title', ''),
                    caption=c.get('caption', ''),
                    hashtags_json=json.dumps(c.get('hashtags', [])),
                    platform_meta_json=json.dumps({
                        "tiktok_titles": c.get("tiktok_titles", []),
                        "reels_titles": c.get("reels_titles", []),
                        "shorts_titles": c.get("shorts_titles", []),
                        "tiktok_hashtags": c.get("tiktok_hashtags", []),
                        "reels_hashtags": c.get("reels_hashtags", []),
                        "shorts_hashtags": c.get("shorts_hashtags", []),
                        "tiktok_caption": c.get("tiktok_caption", ""),
                        "reels_caption": c.get("reels_caption", ""),
                        "shorts_caption": c.get("shorts_caption", ""),
                        "is_montage": getattr(clip, "is_montage", False),
                        "segments": seg_list
                    }),
                    output_path=output_paths[idx] if idx < len(output_paths) else None,
                    status='COMPLETED'
                ))
            session.add_all(clip_objs)
            job.output_video_path = ",".join(output_paths)
                
            job.status = JobStatus.COMPLETED
            job.progress_percentage = 100
            job.current_step_message = "Completed successfully."
            await session.commit()

            # Dispatch Webhook Notification (use user custom webhook or default Telegram webhook)
            target_webhook = (job.webhook_url or "").strip() or settings.DEFAULT_WEBHOOK_URL
            if target_webhook:
                from services.notifications import send_webhook_notification
                await send_webhook_notification(target_webhook, job_id, job.video_title or "Viral Video", clips_data)

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_log = str(traceback.format_exc())
            job.current_step_message = f"Error: {str(e)}"
            await session.commit()
            
            target_webhook = (job.webhook_url or "").strip() or settings.DEFAULT_WEBHOOK_URL
            if target_webhook:
                from services.notifications import send_failure_notification
                await send_failure_notification(target_webhook, job_id, str(e))
            
            raw_video_path = os.path.join(settings.STORAGE_DIR, "temp", f"{job_id}.mp4")
            if os.path.exists(raw_video_path):
                os.remove(raw_video_path)
        finally:
            active_tasks.pop(job_id, None)
            active_subprocesses.pop(job_id, None)
            # Clean up per-job raw_video_path (cached video in cache_*.mp4 remains for 6 hours)
            raw_video_path = os.path.join(settings.STORAGE_DIR, "temp", f"{job_id}.mp4")
            if os.path.exists(raw_video_path):
                try:
                    os.remove(raw_video_path)
                except Exception:
                    pass
            await session.close()


@app.post("/api/v1/clips", response_model=ClipResponse, status_code=202)
async def create_clip(request: ClipRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    raw_urls = request.youtube_urls
    
    youtube_pattern = re.compile(r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+')
    valid_urls = [u for u in raw_urls if youtube_pattern.match(u)][:5] # Limit max 5 URLs per batch
    
    if not valid_urls:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL. Please provide valid youtube.com or youtu.be link(s).")
    
    job_ids = []
    for index, url_str in enumerate(valid_urls):
        new_job = VideoJob(
            youtube_url=url_str,
            aspect_ratio=request.aspect_ratio,
            subtitle_color=request.subtitle_color,
            subtitle_size=request.subtitle_size,
            subtitle_opacity=request.subtitle_opacity,
            subtitle_preset=request.subtitle_preset,
            subtitle_position=request.subtitle_position,
            target_language=request.target_language,
            crop_style=request.crop_style,
            enable_subtitles=request.enable_subtitles,
            custom_prompt=request.custom_prompt,
            clip_count=request.clip_count,
            auto_reframe=request.auto_reframe,
            word_karaoke=request.word_karaoke,
            bgm_ducking=request.bgm_ducking,
            layout_mode=request.layout_mode,
            clip_mode=getattr(request, "clip_mode", "single") or "single",
            watermark_position=request.watermark_position,
            watermark_path=request.watermark_path,
            enable_sfx=request.enable_sfx,
            webhook_url=request.webhook_url,
            gemini_api_key=request.gemini_api_key,
            target_keyword=request.target_keyword,
            target_start_time=request.target_start_time,
            target_end_time=request.target_end_time,
            status=JobStatus.QUEUED,
            current_step_message=f"Enqueued in background batch ({index+1}/{len(valid_urls)})."
        )
        db.add(new_job)
        await db.commit()
        await db.refresh(new_job)
        job_ids.append(new_job.id)
        background_tasks.add_task(process_video_pipeline, new_job.id)
        
    return ClipResponse(job_id=job_ids[0], job_ids=job_ids, status=JobStatus.QUEUED)


@app.post("/api/v1/upload", response_model=ClipResponse)
async def upload_local_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    aspect_ratio: str = Form("9:16"),
    subtitle_color: str = Form("&H00FFFF"),
    subtitle_size: int = Form(90),
    subtitle_opacity: int = Form(100),
    subtitle_preset: str = Form("hormozi"),
    subtitle_position: str = Form("bottom"),
    target_language: str = Form("id"),
    crop_style: str = Form("center_crop"),
    enable_subtitles: bool = Form(False),
    custom_prompt: str = Form(""),
    clip_count: int = Form(3),
    auto_reframe: bool = Form(False),
    word_karaoke: bool = Form(False),
    bgm_ducking: bool = Form(False),
    layout_mode: str = Form("auto"),
    clip_mode: str = Form("single"),
    watermark_position: str = Form("top_right"),
    watermark_path: str = Form(""),
    enable_sfx: bool = Form(True),
    webhook_url: str = Form(""),
    gemini_api_key: str = Form(""),
    target_keyword: str = Form(""),
    target_start_time: str = Form(""),
    target_end_time: str = Form(""),
    db: AsyncSession = Depends(get_db)
):
    # FIX #1.3: Batas ukuran & validasi ekstensi upload video
    allowed_exts = {".mp4", ".mov", ".mkv", ".webm"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Hanya file .mp4, .mov, .mkv, .webm yang diizinkan")
        
    safe_filename = f"{uuid.uuid4().hex}{ext}"

    new_job = VideoJob(
        youtube_url=f"local://{safe_filename}",
        video_title=file.filename,
        aspect_ratio=aspect_ratio,
        subtitle_color=subtitle_color,
        subtitle_size=subtitle_size,
        subtitle_opacity=subtitle_opacity,
        subtitle_preset=subtitle_preset,
        subtitle_position=subtitle_position,
        target_language=target_language,
        crop_style=crop_style,
        enable_subtitles=enable_subtitles,
        custom_prompt=custom_prompt,
        clip_count=clip_count,
        auto_reframe=auto_reframe,
        word_karaoke=word_karaoke,
        bgm_ducking=bgm_ducking,
        layout_mode=layout_mode,
        clip_mode=clip_mode,
        watermark_position=watermark_position,
        watermark_path=watermark_path,
        enable_sfx=enable_sfx,
        webhook_url=webhook_url,
        gemini_api_key=gemini_api_key,
        target_keyword=target_keyword,
        target_start_time=target_start_time,
        target_end_time=target_end_time,
        status=JobStatus.QUEUED,
        current_step_message="Saving uploaded file to local disk..."
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    
    temp_dir = os.path.join(settings.STORAGE_DIR, "temp")
    raw_video_path = os.path.join(temp_dir, f"{new_job.id}.mp4")
    
    max_size = 2 * 1024 * 1024 * 1024 # 2GB
    total_size = 0
    with open(raw_video_path, "wb") as f:
        while chunk := await file.read(4 * 1024 * 1024):
            total_size += len(chunk)
            if total_size > max_size:
                raise HTTPException(status_code=413, detail="File melebihi batas 2 GB")
            f.write(chunk)
        
    background_tasks.add_task(process_video_pipeline, new_job.id)
    return ClipResponse(job_id=new_job.id, status=new_job.status)


@app.get("/api/v1/clips/history", response_model=List[VideoJobDetail])
async def list_clips(db: AsyncSession = Depends(get_db)):
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(VideoJob)
        .options(selectinload(VideoJob.clips))
        .where(VideoJob.status == JobStatus.COMPLETED)
        .order_by(VideoJob.created_at.desc())
        .limit(20)
    )
    jobs = result.scalars().all()
    return jobs

@app.get("/api/v1/clips/{job_id}", response_model=VideoJobDetail)
async def get_clip(job_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy.orm import selectinload
    job = await db.get(VideoJob, job_id, options=[selectinload(VideoJob.clips)])
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/api/v1/clips/{job_id}/zip")
async def download_job_zip(job_id: str, db: AsyncSession = Depends(get_db)):
    """
    Packages all generated clips (.mp4) and caption text for a completed job into a single .zip file.
    Uses native Python zipfile without third-party bloat.
    """
    from sqlalchemy.orm import selectinload
    import io
    import zipfile
    
    job = await db.get(VideoJob, job_id, options=[selectinload(VideoJob.clips)])
    if not job or not job.clips:
        raise HTTPException(status_code=404, detail="Job or clips not found")
        
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for c in job.clips:
            if c.output_path:
                rel_path = c.output_path.lstrip("/").replace("exports/", "")
                real_file_path = os.path.join(settings.STORAGE_DIR, "exports", rel_path)
                if os.path.exists(real_file_path):
                    zip_file.write(real_file_path, arcname=f"clip_{c.clip_index + 1}_{c.id[:8]}.mp4")
            
            caption_text = f"Hook Title: {c.hook_title or ''}\n\nCaption:\n{c.caption or ''}\n\nHashtags:\n{c.hashtags_json or ''}\n"
            zip_file.writestr(f"caption_clip_{c.clip_index + 1}_{c.id[:8]}.txt", caption_text)
            
    zip_buffer.seek(0)
    filename = f"AutoClip_{job_id[:8]}_all_clips.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/v1/clips/{job_id}/stream")
async def stream_clip_progress(job_id: str):
    """
    Server-Sent Events (SSE) endpoint for real-time progress streaming.
    Streams job status, progress percentage, and step messages instantly.
    """
    async def event_generator():
        last_state = None
        while True:
            try:
                from sqlalchemy.orm import selectinload
                async with AsyncSessionLocal() as session:
                    job = await session.get(VideoJob, job_id, options=[selectinload(VideoJob.clips)])
                    if not job:
                        err_payload = json.dumps({"error": "Job not found", "status": "FAILED"})
                        yield f"data: {err_payload}\n\n"
                        break

                    status_str = str(job.status.value) if hasattr(job.status, "value") else str(job.status)
                    current_state = (status_str, job.progress_percentage, job.current_step_message, job.clips_json)

                    if current_state != last_state:
                        payload = {
                            "id": job.id,
                            "youtube_url": job.youtube_url,
                            "video_title": job.video_title,
                            "aspect_ratio": job.aspect_ratio,
                            "subtitle_color": job.subtitle_color,
                            "subtitle_size": job.subtitle_size,
                            "status": status_str,
                            "progress_percentage": job.progress_percentage,
                            "current_step_message": job.current_step_message or "",
                            "clips_json": job.clips_json or "",
                            "output_video_path": job.output_video_path or "",
                            "error_log": job.error_log or ""
                        }
                        yield f"data: {json.dumps(payload)}\n\n"
                        last_state = current_state

                    if status_str in ["COMPLETED", "FAILED"]:
                        break
            except Exception as e:
                err_data = json.dumps({"error": str(e), "status": "FAILED"})
                yield f"data: {err_data}\n\n"
                break

            await asyncio.sleep(1.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        return templates.TemplateResponse(request=request, name="index.html")
    except Exception as e:
        import traceback
        return HTMLResponse(content=f"<pre>{traceback.format_exc()}</pre>", status_code=500)

class RerenderRequest(BaseModel):
    subtitle_color: str
    subtitle_size: int
    subtitle_preset: str = "hormozi"
    subtitle_position: str = "bottom"
    target_language: str = "id"
    subtitle_opacity: int = 100
    word_karaoke: bool = False
    bgm_ducking: bool = False

@app.post("/api/v1/clips/{job_id}/rerender", status_code=200)
async def rerender_clip(job_id: str, request: RerenderRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    from sqlalchemy.orm import selectinload
    job = await db.get(VideoJob, job_id, options=[selectinload(VideoJob.clips)])
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job.subtitle_color = request.subtitle_color
    job.subtitle_size = request.subtitle_size
    job.subtitle_preset = request.subtitle_preset
    job.subtitle_position = request.subtitle_position
    job.target_language = request.target_language
    job.subtitle_opacity = request.subtitle_opacity
    job.word_karaoke = request.word_karaoke
    job.bgm_ducking = request.bgm_ducking
    job.status = JobStatus.EDITING
    job.progress_percentage = 80
    job.current_step_message = "Re-rendering clips with new settings..."
    await db.commit()
    
    async def process_rerender(jid: str, opacity: int):
        from database import AsyncSessionLocal
        session = AsyncSessionLocal()
        try:
            from sqlalchemy.orm import selectinload
            j = await session.get(VideoJob, jid, options=[selectinload(VideoJob.clips)])
            if not j:
                return
            try:
                raw_video_path = await ensure_source_video(j)
                clips_data = json.loads(j.clips_json) if j.clips_json else []
                output_paths = []
                temp_dir = os.path.join(settings.STORAGE_DIR, "temp")
                
                for clip_dict in clips_data:
                    clip_id = clip_dict.get("id")
                    start_time = clip_dict.get("start_time")
                    end_time = clip_dict.get("end_time")
                    hook_title_text = clip_dict.get("hook_title", "")
                    
                    # Re-generate ASS Subtitle with updated styling, position, & translation
                    from services.whisper_stt import generate_whisper_srt
                    srt_text = await generate_whisper_srt(
                        raw_video_path, start_time, end_time, temp_dir, clip_id,
                        sub_size=j.subtitle_size, sub_color=j.subtitle_color, word_karaoke=j.word_karaoke,
                        hook_title=hook_title_text, subtitle_preset=getattr(j, "subtitle_preset", "hormozi"),
                        subtitle_position=getattr(j, "subtitle_position", "bottom"),
                        target_language=getattr(j, "target_language", "id"),
                        sub_opacity=getattr(j, "subtitle_opacity", 100)
                    )
                    
                    subtitle_path = None
                    if srt_text:
                        subtitle_path = os.path.join(settings.STORAGE_DIR, "temp", f"{jid}_{clip_id}_rerender.ass")
                        with open(subtitle_path, "w", encoding="utf-8") as f:
                            f.write(srt_text)
                            
                    export_path = os.path.join(settings.STORAGE_DIR, "exports", f"{jid}_{clip_id}_rerender.mp4")
                    
                    if os.path.exists(export_path):
                        os.remove(export_path)
                    
                    job_settings = {
                        "aspect_ratio": j.aspect_ratio,
                        "subtitle_color": j.subtitle_color,
                        "subtitle_size": j.subtitle_size,
                        "crop_style": j.crop_style,
                        "auto_reframe": j.auto_reframe,
                        "word_karaoke": j.word_karaoke,
                        "bgm_ducking": j.bgm_ducking,
                        "subtitle_opacity": opacity,
                        "watermark_path": getattr(j, "watermark_path", None),
                        "watermark_position": getattr(j, "watermark_position", "top_right"),
                        "custom_font_path": getattr(j, "custom_font_path", None),
                        "enable_sfx": getattr(j, "enable_sfx", True),
                        "layout_mode": getattr(j, "layout_mode", "auto")
                    }
                    
                    from services.ffmpeg import render_viral_clip
                    await render_viral_clip(raw_video_path, export_path, start_time, end_time, subtitle_path, job_settings, burn_subtitles=getattr(j, "enable_subtitles", False))
                    output_paths.append(f"/exports/{jid}_{clip_id}_rerender.mp4")
                    
                    if subtitle_path and os.path.exists(subtitle_path):
                        os.remove(subtitle_path)
                        
                j.output_video_path = ",".join(output_paths)
                j.status = JobStatus.COMPLETED
                j.progress_percentage = 100
                j.current_step_message = "Re-render completed successfully."
                await session.commit()
            except Exception as e:
                j.status = JobStatus.FAILED
                j.error_log = str(e)
                j.current_step_message = "Re-render failed."
                await session.commit()
        finally:
            await session.close()
                
    background_tasks.add_task(process_rerender, job_id, request.subtitle_opacity)
    return {"message": "Re-render started", "job_id": job_id}


class RetrimRequest(BaseModel):
    clip_index: int
    start_time: str
    end_time: str
    crop_style: Optional[str] = None
    layout_mode: Optional[str] = None

@app.post("/api/v1/clips/{job_id}/retrim")
async def retrim_clip_endpoint(job_id: str, request: RetrimRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    from sqlalchemy.orm import selectinload
    job = await db.get(VideoJob, job_id, options=[selectinload(VideoJob.clips)])
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if request.crop_style:
        job.crop_style = request.crop_style
    if request.layout_mode:
        job.layout_mode = request.layout_mode

    if not job.clips or request.clip_index < 0 or request.clip_index >= len(job.clips):
        raise HTTPException(status_code=400, detail="Invalid clip index")
        
    from utils.timestamp import parse_timestamp
    target_clip = job.clips[request.clip_index]
    target_clip.start_sec = int(parse_timestamp(request.start_time))
    target_clip.end_sec = int(parse_timestamp(request.end_time))
    await db.commit()
    job.status = JobStatus.EDITING
    job.progress_percentage = 80
    job.current_step_message = f"Re-trimming clip #{request.clip_index+1} ({request.start_time} - {request.end_time})..."
    await db.commit()
    
    async def process_retrim(jid: str, idx: int):
        from database import AsyncSessionLocal
        session = AsyncSessionLocal()
        try:
            from sqlalchemy.orm import selectinload
            j = await session.get(VideoJob, jid, options=[selectinload(VideoJob.clips)])
            if not j:
                return
            if not j.clips or idx < 0 or idx >= len(j.clips):
                return
            db_clip = j.clips[idx]
            clip_id = db_clip.id
            raw_video_path = await ensure_source_video(j)
            temp_dir = os.path.join(settings.STORAGE_DIR, "temp")
            export_path = os.path.join(settings.STORAGE_DIR, "exports", f"{jid}_{clip_id}.mp4")
            
            from services.whisper_stt import generate_whisper_srt
            whisper_srt = await generate_whisper_srt(
                raw_video_path, db_clip.start_sec, db_clip.end_sec, temp_dir, clip_id,
                sub_size=j.subtitle_size, sub_color=j.subtitle_color, word_karaoke=j.word_karaoke,
                hook_title=db_clip.hook_title or "", subtitle_preset=getattr(j, "subtitle_preset", "hormozi"),
                subtitle_position=getattr(j, "subtitle_position", "bottom"),
                target_language=getattr(j, "target_language", "id"),
                sub_opacity=getattr(j, "subtitle_opacity", 100)
            )
            
            subtitle_path = None
            if whisper_srt:
                subtitle_path = os.path.join(temp_dir, f"{jid}_{clip_id}_retrim.ass")
                with open(subtitle_path, "w", encoding="utf-8") as f:
                    f.write(whisper_srt)
                    
            job_settings = {
                "aspect_ratio": j.aspect_ratio,
                "subtitle_color": j.subtitle_color,
                "subtitle_size": j.subtitle_size,
                "crop_style": j.crop_style,
                "auto_reframe": j.auto_reframe,
                "word_karaoke": j.word_karaoke,
                "bgm_ducking": j.bgm_ducking,
                "watermark_path": getattr(j, "watermark_path", None),
                "watermark_position": getattr(j, "watermark_position", "top_right"),
                "custom_font_path": getattr(j, "custom_font_path", None),
                "enable_sfx": getattr(j, "enable_sfx", True),
                "layout_mode": getattr(j, "layout_mode", "auto")
            }
            await render_viral_clip(raw_video_path, export_path, db_clip.start_sec, db_clip.end_sec, subtitle_path, job_settings, burn_subtitles=getattr(j, "enable_subtitles", False))
            
            # Re-generate 3 AI Thumbnails - DISABLED BY USER REQUEST
            # from services.ffmpeg import generate_viral_thumbnails
            # thumb_vars = await generate_viral_thumbnails(raw_video_path, db_clip.start_sec, db_clip.end_sec, db_clip.hook_title or "", export_path)
            db_clip.output_path = f"/exports/{os.path.basename(export_path)}"
            db_clip.status = 'COMPLETED'
            j.status = JobStatus.COMPLETED
            j.progress_percentage = 100
            j.current_step_message = "Re-trim completed successfully."
            await session.commit()
        except Exception as e:
            j.status = JobStatus.FAILED
            j.error_log = str(e)
            await session.commit()
        finally:
            await session.close()
            
    background_tasks.add_task(process_retrim, job_id, request.clip_index)
    return {"message": "Re-trim processing started", "job_id": job_id}


@app.post("/api/v1/upload_watermark")
async def upload_watermark(file: UploadFile = File(...)):
    # FIX #1.2: Validasi watermark, uuid, size 10MB, PIL verify
    ext = Path(file.filename).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(400, "Ekstensi watermark tidak diizinkan")
    
    max_size = 10 * 1024 * 1024
    total_size = 0
    file_bytes = b""
    while chunk := await file.read(1024 * 1024):
        total_size += len(chunk)
        if total_size > max_size:
            raise HTTPException(413, "Ukuran maksimal 10 MB")
        file_bytes += chunk
        
    try:
        Image.open(io.BytesIO(file_bytes)).verify()
    except UnidentifiedImageError:
        raise HTTPException(400, "File bukan gambar yang valid")

    asset_dir = os.path.join(os.path.dirname(__file__), "assets")
    os.makedirs(asset_dir, exist_ok=True)
    safe_name = f"wm_{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(asset_dir, safe_name)
    with open(save_path, "wb") as f:
        f.write(file_bytes)
    return {"watermark_path": save_path, "filename": safe_name}


@app.post("/api/v1/upload_font")
async def upload_font(file: UploadFile = File(...)):
    # FIX #1.2: Validasi font, uuid, size 20MB
    ext = Path(file.filename).suffix.lower()
    if ext not in {".ttf", ".otf"}:
        raise HTTPException(400, "Ekstensi font tidak diizinkan")
        
    max_size = 20 * 1024 * 1024
    total_size = 0
    file_bytes = b""
    while chunk := await file.read(1024 * 1024):
        total_size += len(chunk)
        if total_size > max_size:
            raise HTTPException(413, "Ukuran maksimal 20 MB")
        file_bytes += chunk

    fonts_dir = os.path.join(os.path.dirname(__file__), "assets", "fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(fonts_dir, safe_name)
    with open(save_path, "wb") as f:
        f.write(file_bytes)
    return {"font_path": save_path, "filename": safe_name}


class TikTokPublishRequest(BaseModel):
    video_path: str
    access_token: Optional[str] = None
    title: Optional[str] = ""
    privacy_level: Optional[str] = "SELF_ONLY"
    post_mode: Optional[str] = "inbox"

class TelegramSendRequest(BaseModel):
    video_path: str
    caption: Optional[str] = ""

@app.post("/api/v1/telegram/send_mp4")
async def telegram_send_mp4_endpoint(req: TelegramSendRequest):
    try:
        from config import settings
        import os
        import httpx
        
        full_video_path = str(validate_export_path(req.video_path))
        if not os.path.exists(full_video_path):
            raise HTTPException(status_code=404, detail="MP4 file not found")
            
        file_size_mb = os.path.getsize(full_video_path) / (1024 * 1024)
        if file_size_mb > 49.5:
            raise HTTPException(status_code=400, detail=f"Ukuran file ({file_size_mb:.1f} MB) terlalu besar! Batas maksimal Telegram Bot adalah 50MB.")
            
        webhook_url = settings.DEFAULT_WEBHOOK_URL
        if not webhook_url or ("tg:" not in webhook_url and "api.telegram.org" not in webhook_url):
            raise HTTPException(status_code=400, detail="Telegram Bot Token/Chat ID not configured in .env")
            
        if webhook_url.startswith("tg:"):
            parts = webhook_url.split(":")
            bot_token = f"{parts[1]}:{parts[2]}"
            chat_id = parts[3]
        else:
            bot_token = webhook_url.split("/bot")[1].split("/")[0]
            chat_id = webhook_url.split("chat_id=")[1].split("&")[0]
            
        url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
        
        with open(full_video_path, "rb") as f:
            async with httpx.AsyncClient(timeout=300.0) as client:
                res = await client.post(
                    url,
                    data={"chat_id": chat_id, "caption": req.caption[:1024]},
                    files={"video": f}
                )
        
        if res.status_code == 200:
            return {"status": "success", "message": "MP4 sent to Telegram successfully"}
        else:
            raise HTTPException(status_code=res.status_code, detail=res.text)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")

@app.post("/api/v1/tiktok/publish")
async def publish_to_tiktok_endpoint(req: TikTokPublishRequest):
    # FIX #1.1: Path traversal protection
    full_video_path = str(validate_export_path(req.video_path))

    from config import Settings
    current_settings = Settings()
    token_to_use = req.access_token or current_settings.TIKTOK_ACCESS_TOKEN or os.getenv("TIKTOK_ACCESS_TOKEN")

    res = await publish_video_to_tiktok(
        full_video_path,
        token_to_use,
        title=req.title or "",
        privacy_level=req.privacy_level or "SELF_ONLY",
        post_mode=req.post_mode or "inbox"
    )
    if res.get("status") == "error":
        msg = res.get("message") or "TikTok publishing failed with unknown error"
        raise HTTPException(status_code=400, detail=msg)
        
    # Send instant Telegram Bot notification with TikTok caption & copyable block
    try:
        from services.notifications import send_tiktok_publish_telegram_notification
        await send_tiktok_publish_telegram_notification(
            webhook_url="",
            title=os.path.basename(full_video_path),
            caption=req.title or "",
            mode=req.post_mode or "inbox",
            publish_id=res.get("publish_id", "")
        )
    except Exception as notify_err:
        print(f"[TikTok Notify Trigger Error] {notify_err}")

    return res

@app.get("/api/v1/tiktok/login")
async def tiktok_login_redirect():
    url = f"https://www.tiktok.com/v2/auth/authorize/?client_key={settings.TIKTOK_CLIENT_KEY}&response_type=code&scope=user.info.basic,video.upload,video.publish&redirect_uri=https://autoclipweb.com/api/v1/tiktok/callback&state=auto_clip_web"
    return RedirectResponse(url)

@app.get("/api/v1/tiktok/callback")
async def tiktok_oauth_callback(code: str = ""):
    if not code:
        return {"error": "No code parameter found in callback URL"}
        
    url = "https://open.tiktokapis.com/v2/oauth/token/"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cache-Control": "no-cache"
    }
    data = {
        "client_key": settings.TIKTOK_CLIENT_KEY,
        "client_secret": settings.TIKTOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": "https://autoclipweb.com/api/v1/tiktok/callback"
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post(url, data=data, headers=headers)
        return res.json()


@app.post("/api/v1/tiktok/refresh")
async def refresh_tiktok_token_endpoint(refresh_token: str = ""):
    from services.tiktok_publisher import refresh_tiktok_access_token
    token_to_use = refresh_token or settings.TIKTOK_REFRESH_TOKEN
    res = await refresh_tiktok_access_token(settings.TIKTOK_CLIENT_KEY, settings.TIKTOK_CLIENT_SECRET, token_to_use)
    return res



@app.post("/api/v1/storage/cleanup")
async def trigger_storage_cleanup():
    """Manual trigger to clean up old temp and export files instantly."""
    from services.garbage_collector import run_storage_cleanup
    res = await run_storage_cleanup(temp_max_age_hours=24, export_max_age_days=3)
    return res




@app.post("/api/v1/clips/{job_id}/cancel")
async def cancel_job(job_id: str, db: AsyncSession = Depends(get_db)):
    from models import VideoJob, JobStatus
    job = await db.get(VideoJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        return {"status": "ignored", "message": "Job is already finished"}
        
    job.status = JobStatus.CANCELLED
    job.current_step_message = "Cancelling..."
    await db.commit()
    
    # 1. Cancel asyncio Task if running
    task = active_tasks.get(job_id)
    if task and not task.done():
        task.cancel()
        
    # 2. Terminate Subprocess if any
    proc = active_subprocesses.get(job_id)
    if proc:
        try:
            proc.terminate()
        except Exception:
            pass
            
    return {"status": "success", "message": "Job cancellation initiated"}

@app.get("/api/v1/health")
async def health_check():
    import shutil
    import aiosqlite
    from database import engine
    from services.ffmpeg import check_nvenc_availability
    
    health = {"status": "ok_v2"}
    
    # Check DB
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        health["db"] = "connected"
    except Exception as e:
        import traceback
        traceback.print_exc()
        health["db"] = f"error: {str(e)}"
        health["status"] = "degraded"
        
    # Check Disk Space
    try:
        free_gb = shutil.disk_usage(settings.STORAGE_DIR).free / (1024**3)
        health["disk_free_gb"] = round(free_gb, 2)
        if free_gb < 5:
            health["status"] = "degraded"
    except Exception as e:
        health["disk"] = f"error: {str(e)}"
        
    # Check FFmpeg Encoder
    try:
        has_nvenc = await check_nvenc_availability()
        health["ffmpeg_encoder"] = "h264_nvenc" if has_nvenc else "libx264"
    except Exception as e:
        health["ffmpeg_encoder"] = "error"
        
    return health

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)

