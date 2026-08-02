from fastapi import FastAPI, BackgroundTasks, Depends, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import asyncio
import os
import yt_dlp
import traceback
import json
import re
import subprocess
from datetime import datetime, timedelta
from typing import List, Optional

import httpx

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

def cleanup_temp_storage():
    """Cleans up orphan audio and subtitle temporary files older than 24 hours."""
    temp_dir = os.path.join(settings.STORAGE_DIR, "temp")
    if not os.path.exists(temp_dir):
        return
    now = datetime.now()
    for fname in os.listdir(temp_dir):
        if fname.endswith((".wav", ".ass", ".mp3")):
            fpath = os.path.join(temp_dir, fname)
            try:
                file_time = datetime.fromtimestamp(os.path.getmtime(fpath))
                if now - file_time > timedelta(hours=24):
                    os.remove(fpath)
            except Exception:
                pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    cleanup_temp_storage()
    from services.notifications import start_telegram_bot_listener
    from services.garbage_collector import start_storage_garbage_collector
    listener_task = asyncio.create_task(start_telegram_bot_listener())
    gc_task = asyncio.create_task(start_storage_garbage_collector(check_interval_hours=6))
    yield
    listener_task.cancel()
    gc_task.cancel()

app = FastAPI(title="AI Auto-Clipper API", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return HTMLResponse(content=f"<pre>{traceback.format_exc()}</pre>", status_code=500)

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return HTMLResponse(content="", status_code=204)

os.makedirs(os.path.join(settings.STORAGE_DIR, "exports"), exist_ok=True)
app.mount("/exports", StaticFiles(directory=os.path.join(settings.STORAGE_DIR, "exports")), name="exports")

async def process_video_pipeline(job_id: str):
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
                cmd = [
                    "python", "-m", "yt_dlp",
                    "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
                    "--merge-output-format", "mp4",
                    "-o", raw_video_path,
                    "--quiet",
                    "--no-warnings",
                    "--dump-json",
                    "--no-simulate",
                    "--retries", "10",
                    "--fragment-retries", "10",
                    "--socket-timeout", "30",
                    "--concurrent-fragments", "5",
                    "--js-runtimes", "node"
                ]
                
                cookies_txt = os.path.abspath("cookies.txt")
                if os.path.exists(cookies_txt):
                    cmd.extend(["--cookies", cookies_txt])
                    
                cmd.append(job.youtube_url)
                
                def run_yt_dlp(command):
                    return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    
                process = await asyncio.to_thread(run_yt_dlp, cmd)
                stdout, stderr = process.stdout, process.stderr
                
                if process.returncode != 0:
                    error_msg = stderr.decode('utf-8', errors='ignore').strip()
                    # If bot verification triggered, try with browser cookies fallback
                    if "bot" in error_msg.lower() or "sign in" in error_msg.lower():
                        print("[yt-dlp] Bot detection triggered. Retrying with Chrome browser cookies...")
                        cookie_cmd = list(cmd)
                        cookie_cmd.extend(["--cookies-from-browser", "chrome"])
                        process = await asyncio.to_thread(run_yt_dlp, cookie_cmd)
                        stdout, stderr = process.stdout, process.stderr
                        if process.returncode != 0:
                            cookie_cmd2 = list(cmd)
                            cookie_cmd2.extend(["--cookies-from-browser", "edge"])
                            process = await asyncio.to_thread(run_yt_dlp, cookie_cmd2)
                            stdout, stderr = process.stdout, process.stderr
                    
                    if process.returncode != 0:
                        error_msg = stderr.decode('utf-8', errors='ignore').strip()
                        raise Exception(f"Video unavailable or invalid URL (yt-dlp failed): {error_msg}")
                    
                try:
                    info = json.loads(stdout.decode('utf-8', errors='ignore'))
                    title = info.get('title', 'Unknown Title')
                    duration = info.get('duration', 0)
                except Exception:
                    title = 'Local Video'
                    duration = 0
                
            job.video_title = title
            job.duration_seconds = duration
            await session.commit()

            # Step 2: ANALYZING (Audio only to save huge tokens)
            job.status = JobStatus.ANALYZING
            job.progress_percentage = 40
            job.current_step_message = "Extracting audio for AI analysis (saving tokens)..."
            await session.commit()
            
            audio_path = os.path.join(temp_dir, f"{job_id}.mp3")
            audio_cmd = ["ffmpeg", "-y", "-i", raw_video_path, "-vn", "-c:a", "libmp3lame", "-q:a", "5", audio_path]
            audio_process = await asyncio.to_thread(subprocess.run, audio_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if audio_process.returncode != 0:
                raise Exception("Failed to extract audio for analysis.")
                
            job.progress_percentage = 45
            job.current_step_message = "Analyzing viral moments with Gemini Auto-Fallback Engine..."
            await session.commit()
            
            analysis = await analyze_video(audio_path, job.custom_prompt, job.clip_count, custom_api_key=getattr(job, "gemini_api_key", "") or "")
            
            # Cleanup audio
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            # Step 3: EDITING
            job.status = JobStatus.EDITING
            job.progress_percentage = 75
            
            clips_data = []
            output_paths = []
            for i, clip in enumerate(analysis.clips):
                job.current_step_message = f"Transcribing clip {i+1}/{len(analysis.clips)} with Whisper (frame-accurate)..."
                job.progress_percentage = 75 + int((i / len(analysis.clips)) * 10)
                await session.commit()
                
                hook_title_text = getattr(clip, "hook_title", "")
                
                # Use Whisper for frame-accurate subtitle timestamps, karaoke styling, presets, positioning, translation, and hook banner
                whisper_srt = await generate_whisper_srt(
                    raw_video_path, clip.start_time, clip.end_time, temp_dir, clip.id,
                    sub_size=job.subtitle_size, sub_color=job.subtitle_color, word_karaoke=job.word_karaoke,
                    hook_title=hook_title_text, subtitle_preset=getattr(job, "subtitle_preset", "hormozi"),
                    subtitle_position=getattr(job, "subtitle_position", "bottom"),
                    target_language=getattr(job, "target_language", "id")
                )
                
                cover_export_path = os.path.join(settings.STORAGE_DIR, "exports", f"{job_id}_{clip.id}_cover.jpg")
                
                clips_data.append({
                    "id": clip.id,
                    "start_time": clip.start_time,
                    "end_time": clip.end_time,
                    "viral_score": clip.viral_score,
                    "hook_title": hook_title_text,
                    "caption": clip.caption,
                    "hashtags": clip.hashtags,
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
                    "has_broll": getattr(clip, "has_broll", False)
                }
                await render_viral_clip(raw_video_path, export_path, clip.start_time, clip.end_time, subtitle_path, job_settings, burn_subtitles=True)
                
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
                    
            job.clips_json = json.dumps(clips_data)
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
            await session.close()


@app.post("/api/v1/clips", response_model=ClipResponse, status_code=202)
async def create_clip(request: ClipRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    raw_input = str(request.youtube_url).strip()
    raw_urls = [u.strip() for u in re.split(r'[\r\n,\s]+', raw_input) if u.strip()]
    
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
            subtitle_preset=request.subtitle_preset,
            subtitle_position=request.subtitle_position,
            target_language=request.target_language,
            crop_style=request.crop_style,
            custom_prompt=request.custom_prompt,
            clip_count=request.clip_count,
            auto_reframe=request.auto_reframe,
            word_karaoke=request.word_karaoke,
            bgm_ducking=request.bgm_ducking,
            layout_mode=request.layout_mode,
            watermark_position=request.watermark_position,
            watermark_path=request.watermark_path,
            enable_sfx=request.enable_sfx,
            webhook_url=request.webhook_url,
            gemini_api_key=request.gemini_api_key,
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
    subtitle_preset: str = Form("hormozi"),
    subtitle_position: str = Form("bottom"),
    target_language: str = Form("id"),
    crop_style: str = Form("center_crop"),
    custom_prompt: str = Form(""),
    clip_count: int = Form(3),
    auto_reframe: bool = Form(False),
    word_karaoke: bool = Form(False),
    bgm_ducking: bool = Form(False),
    layout_mode: str = Form("auto"),
    watermark_position: str = Form("top_right"),
    watermark_path: str = Form(""),
    enable_sfx: bool = Form(True),
    webhook_url: str = Form(""),
    gemini_api_key: str = Form(""),
    db: AsyncSession = Depends(get_db)
):
    new_job = VideoJob(
        youtube_url=f"local://{file.filename}",
        video_title=file.filename,
        aspect_ratio=aspect_ratio,
        subtitle_color=subtitle_color,
        subtitle_size=subtitle_size,
        subtitle_preset=subtitle_preset,
        subtitle_position=subtitle_position,
        target_language=target_language,
        crop_style=crop_style,
        custom_prompt=custom_prompt,
        clip_count=clip_count,
        auto_reframe=auto_reframe,
        word_karaoke=word_karaoke,
        bgm_ducking=bgm_ducking,
        layout_mode=layout_mode,
        watermark_position=watermark_position,
        watermark_path=watermark_path,
        enable_sfx=enable_sfx,
        webhook_url=webhook_url,
        gemini_api_key=gemini_api_key,
        status=JobStatus.QUEUED,
        current_step_message="Saving uploaded file to local disk..."
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    
    temp_dir = os.path.join(settings.STORAGE_DIR, "temp")
    raw_video_path = os.path.join(temp_dir, f"{new_job.id}.mp4")
    
    with open(raw_video_path, "wb") as f:
        content = await file.read()
        f.write(content)
        
    background_tasks.add_task(process_video_pipeline, new_job.id)
    return ClipResponse(job_id=new_job.id, status=new_job.status)


@app.get("/api/v1/clips/history", response_model=List[VideoJobDetail])
async def list_clips(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(VideoJob)
        .where(VideoJob.status == JobStatus.COMPLETED)
        .order_by(VideoJob.created_at.desc())
        .limit(20)
    )
    jobs = result.scalars().all()
    return jobs

@app.get("/api/v1/clips/{job_id}", response_model=VideoJobDetail)
async def get_clip(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(VideoJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


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
                async with AsyncSessionLocal() as session:
                    job = await session.get(VideoJob, job_id)
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

@app.post("/api/v1/clips/{job_id}/rerender", status_code=200)
async def rerender_clip(job_id: str, request: RerenderRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    job = await db.get(VideoJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job.subtitle_color = request.subtitle_color
    job.subtitle_size = request.subtitle_size
    job.subtitle_preset = request.subtitle_preset
    job.subtitle_position = request.subtitle_position
    job.target_language = request.target_language
    job.word_karaoke = request.word_karaoke
    job.status = JobStatus.EDITING
    job.progress_percentage = 80
    job.current_step_message = "Re-rendering clips with new settings..."
    await db.commit()
    
    async def process_rerender(jid: str, opacity: int):
        from database import AsyncSessionLocal
        session = AsyncSessionLocal()
        try:
            j = await session.get(VideoJob, jid)
            if not j:
                return
            try:
                raw_video_path = os.path.join(settings.STORAGE_DIR, "temp", f"{jid}.mp4")
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
                        target_language=getattr(j, "target_language", "id")
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
                    await render_viral_clip(raw_video_path, export_path, start_time, end_time, subtitle_path, job_settings, burn_subtitles=True)
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
    job = await db.get(VideoJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if request.crop_style:
        job.crop_style = request.crop_style
    if request.layout_mode:
        job.layout_mode = request.layout_mode

    clips_data = json.loads(job.clips_json) if job.clips_json else []
    if request.clip_index < 0 or request.clip_index >= len(clips_data):
        raise HTTPException(status_code=400, detail="Invalid clip index")
        
    clips_data[request.clip_index]["start_time"] = request.start_time
    clips_data[request.clip_index]["end_time"] = request.end_time
    job.clips_json = json.dumps(clips_data)
    job.status = JobStatus.EDITING
    job.progress_percentage = 80
    job.current_step_message = f"Re-trimming clip #{request.clip_index+1} ({request.start_time} - {request.end_time})..."
    await db.commit()
    
    async def process_retrim(jid: str, idx: int):
        from database import AsyncSessionLocal
        session = AsyncSessionLocal()
        try:
            j = await session.get(VideoJob, jid)
            if not j:
                return
            c_data = json.loads(j.clips_json) if j.clips_json else []
            target_clip = c_data[idx]
            clip_id = target_clip.get("id")
            raw_video_path = os.path.join(settings.STORAGE_DIR, "temp", f"{jid}.mp4")
            temp_dir = os.path.join(settings.STORAGE_DIR, "temp")
            export_path = os.path.join(settings.STORAGE_DIR, "exports", f"{jid}_{clip_id}.mp4")
            
            from services.whisper_stt import generate_whisper_srt
            whisper_srt = await generate_whisper_srt(
                raw_video_path, target_clip["start_time"], target_clip["end_time"], temp_dir, clip_id,
                sub_size=j.subtitle_size, sub_color=j.subtitle_color, word_karaoke=j.word_karaoke,
                hook_title=target_clip.get("hook_title", ""), subtitle_preset=getattr(j, "subtitle_preset", "hormozi"),
                subtitle_position=getattr(j, "subtitle_position", "bottom"),
                target_language=getattr(j, "target_language", "id")
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
            await render_viral_clip(raw_video_path, export_path, target_clip["start_time"], target_clip["end_time"], subtitle_path, job_settings, burn_subtitles=True)
            
            # Re-generate 3 AI Thumbnails - DISABLED BY USER REQUEST
            # from services.ffmpeg import generate_viral_thumbnails
            # thumb_vars = await generate_viral_thumbnails(raw_video_path, target_clip["start_time"], target_clip["end_time"], target_clip.get("hook_title", ""), export_path)
            # c_data[idx]["thumbnail_variants"] = [f"/exports/{os.path.basename(p)}" for p in thumb_vars]
            c_data[idx]["thumbnail_variants"] = []
            
            j.clips_json = json.dumps(c_data)
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
    asset_dir = os.path.join(os.path.dirname(__file__), "assets")
    os.makedirs(asset_dir, exist_ok=True)
    save_path = os.path.join(asset_dir, f"wm_{file.filename}")
    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)
    return {"watermark_path": save_path, "filename": file.filename}


@app.post("/api/v1/upload_font")
async def upload_font(file: UploadFile = File(...)):
    fonts_dir = os.path.join(os.path.dirname(__file__), "assets", "fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    save_path = os.path.join(fonts_dir, file.filename)
    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)
    return {"font_path": save_path, "filename": file.filename}


class TikTokPublishRequest(BaseModel):
    video_path: str
    access_token: Optional[str] = None
    title: Optional[str] = ""
    privacy_level: Optional[str] = "SELF_ONLY"
    post_mode: Optional[str] = "inbox"

@app.post("/api/v1/tiktok/publish")
async def publish_to_tiktok_endpoint(req: TikTokPublishRequest):
    clean_path = req.video_path.lstrip("/")
    full_video_path = os.path.join(settings.STORAGE_DIR, clean_path)
    if not os.path.exists(full_video_path):
        full_video_path = os.path.join(settings.STORAGE_DIR, "exports", os.path.basename(clean_path))
        
    if not os.path.exists(full_video_path):
        raise HTTPException(status_code=400, detail=f"Video file not found: {req.video_path}")

    res = await publish_video_to_tiktok(
        full_video_path,
        req.access_token or settings.TIKTOK_ACCESS_TOKEN,
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


@app.post("/api/v1/storage/cleanup")
async def trigger_storage_cleanup():
    """Manual trigger to clean up old temp and export files instantly."""
    from services.garbage_collector import run_storage_cleanup
    res = run_storage_cleanup(temp_max_age_hours=24, export_max_age_days=3)
    return res

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)
