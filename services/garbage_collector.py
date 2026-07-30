import os
import asyncio
from datetime import datetime, timedelta
from config import settings

def run_storage_cleanup(temp_max_age_hours: int = 24, export_max_age_days: int = 3) -> dict:
    """
    Scans storage directories and removes files older than specified thresholds.
    - temp_dir: removes temporary video, audio, and subtitle files older than temp_max_age_hours.
    - exports_dir: removes exported MP4 clips and JPG covers older than export_max_age_days.
    Returns details on deleted files and total bytes freed.
    """
    now = datetime.now()
    deleted_files_count = 0
    total_bytes_freed = 0

    storage_dir = settings.STORAGE_DIR
    temp_dir = os.path.join(storage_dir, "temp")
    exports_dir = os.path.join(storage_dir, "exports")

    # 1. Clean storage/temp/
    if os.path.exists(temp_dir):
        for fname in os.listdir(temp_dir):
            fpath = os.path.join(temp_dir, fname)
            if os.path.isfile(fpath):
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
                try:
                    file_time = datetime.fromtimestamp(os.path.getmtime(fpath))
                    if now - file_time > timedelta(days=export_max_age_days):
                        fsize = os.path.getsize(fpath)
                        os.remove(fpath)
                        deleted_files_count += 1
                        total_bytes_freed += fsize
                except Exception as e:
                    print(f"[GarbageCollector Warning] Failed to delete export file {fname}: {e}")

    mb_freed = total_bytes_freed / (1024 * 1024)
    print(f"[GarbageCollector] Cleaned {deleted_files_count} old files. Freed {mb_freed:.2f} MB of disk space.")
    return {
        "status": "success",
        "deleted_files_count": deleted_files_count,
        "bytes_freed": total_bytes_freed,
        "mb_freed": round(mb_freed, 2)
    }

async def start_storage_garbage_collector(check_interval_hours: int = 6):
    """
    Background loop that runs run_storage_cleanup periodically.
    Runs every `check_interval_hours` hours while server is active.
    """
    print(f"[GarbageCollector] Automatic Storage Garbage Collector started (runs every {check_interval_hours} hours)...")
    while True:
        try:
            run_storage_cleanup(temp_max_age_hours=24, export_max_age_days=3)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[GarbageCollector Error] {e}")
        
        # Sleep for specified interval
        await asyncio.sleep(check_interval_hours * 3600)
