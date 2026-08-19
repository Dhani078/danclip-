import os
import asyncio
from datetime import datetime, timedelta
from config import settings

async def run_storage_cleanup(temp_max_age_hours: int = 6, export_max_age_days: int = 3, source_max_age_days: int = 7) -> dict:
    """
    Scans storage directories and removes files older than specified thresholds.
    - temp_dir: removes temporary video, audio, and subtitle files older than temp_max_age_hours (6 hours).
    - exports_dir: removes exported MP4 clips and JPG covers older than export_max_age_days.
    - sources_dir: removes source videos older than source_max_age_days.
    Returns details on deleted files and total bytes freed.
    """
    now = datetime.now()
    deleted_files_count = 0
    total_bytes_freed = 0
    
    active_jobs_files = set()
    try:
        from database import AsyncSessionLocal
        from models import VideoJob, JobStatus, Clip
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        import hashlib
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(VideoJob).options(selectinload(VideoJob.clips))
                .where(VideoJob.status.in_([JobStatus.QUEUED, JobStatus.DOWNLOADING, JobStatus.ANALYZING, JobStatus.EDITING]))
            )
            jobs = result.scalars().all()
            for job in jobs:
                # Add base job files
                active_jobs_files.add(f"{job.id}.mp4")
                active_jobs_files.add(f"{job.id}.mp3")
                active_jobs_files.add(f"{job.id}.wav")
                
                # Add cache file
                url_clean = (job.youtube_url or "").strip()
                url_hash = hashlib.md5(url_clean.encode('utf-8')).hexdigest()[:16] if url_clean else job.id
                active_jobs_files.add(f"cache_{url_hash}.mp4")
                active_jobs_files.add(f"cache_{url_hash}.json")
                
                for clip in job.clips:
                    active_jobs_files.add(f"{job.id}_{clip.id}.mp4")
                    active_jobs_files.add(f"{job.id}_{clip.id}.ass")
                    active_jobs_files.add(f"{job.id}_{clip.id}_retrim.ass")
                    active_jobs_files.add(f"{job.id}_{clip.id}_rerender.ass")
    except Exception as e:
        print(f"[GarbageCollector Warning] Failed to fetch active jobs: {e}")

    storage_dir = settings.STORAGE_DIR
    temp_dir = os.path.join(storage_dir, "temp")
    exports_dir = os.path.join(storage_dir, "exports")
    sources_dir = os.path.join(storage_dir, "sources")

    # 1. Clean storage/temp/
    if os.path.exists(temp_dir):
        for fname in os.listdir(temp_dir):
            fpath = os.path.join(temp_dir, fname)
            if os.path.isfile(fpath):
                if fname in active_jobs_files:
                    continue
                try:
                    file_time = datetime.fromtimestamp(os.path.getmtime(fpath))
                    if now - file_time > timedelta(hours=temp_max_age_hours):
                        fsize = os.path.getsize(fpath)
                        os.remove(fpath)
                        deleted_files_count += 1
                        total_bytes_freed += fsize
                except Exception as e:
                    print(f"[GarbageCollector Warning] Failed to delete temp file {fname}: {e}")

    # 2. Clean storage/exports/
    if os.path.exists(exports_dir):
        for fname in os.listdir(exports_dir):
            fpath = os.path.join(exports_dir, fname)
            if os.path.isfile(fpath):
                if fname in active_jobs_files:
                    continue
                try:
                    file_time = datetime.fromtimestamp(os.path.getmtime(fpath))
                    if now - file_time > timedelta(days=export_max_age_days):
                        fsize = os.path.getsize(fpath)
                        os.remove(fpath)
                        deleted_files_count += 1
                        total_bytes_freed += fsize
                except Exception as e:
                    print(f"[GarbageCollector Warning] Failed to delete export file {fname}: {e}")

    # 3. Clean storage/sources/
    if os.path.exists(sources_dir):
        for fname in os.listdir(sources_dir):
            fpath = os.path.join(sources_dir, fname)
            if os.path.isfile(fpath):
                if fname in active_jobs_files:
                    continue
                try:
                    file_time = datetime.fromtimestamp(os.path.getmtime(fpath))
                    if now - file_time > timedelta(days=source_max_age_days):
                        fsize = os.path.getsize(fpath)
                        os.remove(fpath)
                        deleted_files_count += 1
                        total_bytes_freed += fsize
                except Exception as e:
                    print(f"[GarbageCollector Warning] Failed to delete source file {fname}: {e}")

    mb_freed = total_bytes_freed / (1024 * 1024)
    print(f"[GarbageCollector] Cleaned {deleted_files_count} old files (>6h temp, >{source_max_age_days}d source). Freed {mb_freed:.2f} MB of disk space.")
    return {
        "status": "success",
        "deleted_files_count": deleted_files_count,
        "bytes_freed": total_bytes_freed,
        "mb_freed": round(mb_freed, 2)
    }

async def start_storage_garbage_collector(check_interval_hours: int = 1):
    """
    Background loop that runs run_storage_cleanup periodically.
    Runs every `check_interval_hours` hours while server is active.
    """
    print(f"[GarbageCollector] Automatic Storage Garbage Collector started (runs every {check_interval_hours} hour(s), cleans temp > 6 hours)...")
    while True:
        try:
            await run_storage_cleanup(temp_max_age_hours=6, export_max_age_days=3)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[GarbageCollector Error] {e}")
        
        # Sleep for specified interval
        await asyncio.sleep(check_interval_hours * 3600)
