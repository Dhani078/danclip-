import os
import httpx
import asyncio
import math

def calculate_schedule_times(num_clips: int, interval_hours: int = 3) -> list:
    """
    Calculates anti-spam scheduled upload timestamps for multiple clips
    with a minimum gap (e.g. 3 hours) between each post.
    """
    from datetime import datetime, timedelta
    now = datetime.now()
    schedule_times = []
    
    for i in range(num_clips):
        scheduled_time = now + timedelta(hours=i * interval_hours)
        schedule_times.append({
            "clip_index": i + 1,
            "scheduled_at": scheduled_time.strftime("%Y-%m-%d %H:%M WIB"),
            "delay_hours": i * interval_hours
        })
    return schedule_times

async def publish_video_to_tiktok(
    video_path: str,
    access_token: str,
    title: str = "",
    privacy_level: str = "SELF_ONLY",
    post_mode: str = "inbox"
) -> dict:
    """
    Publishes a video to TikTok via official Content Posting API v2.
    Supports single-chunk upload for files <= 64 MB and dynamic multi-chunk
    upload for files > 64 MB to satisfy TikTok API chunking constraints.
    """
    if not os.path.exists(video_path):
        return {"status": "error", "message": f"Video file not found: {video_path}"}
        
    if not access_token:
        return {"status": "error", "message": "TikTok Access Token is missing. Please provide a valid Access Token."}

    file_size = os.path.getsize(video_path)
    
    # TikTok API constraint: single chunk max size is 64 MB (67,108,864 bytes).
    MAX_SINGLE_CHUNK = 64 * 1024 * 1024  # 64 MB
    
    if file_size <= MAX_SINGLE_CHUNK:
        chunk_size = file_size
        total_chunks = 1
    else:
        total_chunks = math.ceil(file_size / MAX_SINGLE_CHUNK)
        chunk_size = file_size // total_chunks
    
    # 1. Step 1: Initialize Upload Session
    # Direct Post uses /v2/post/publish/video/init/ (direct to Feed with caption)
    # Inbox Post uses /v2/post/publish/inbox/video/init/ (to Inbox Drafts)
    if post_mode == "direct" or privacy_level == "PUBLIC_TO_EVERYONE":
        init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    else:
        init_url = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunks
        }
    }
    
    if title:
        payload["post_info"] = {
            "title": title[:2200],
            "privacy_level": privacy_level or "SELF_ONLY"
        }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            init_res = await client.post(init_url, json=payload, headers=headers)
            init_data = init_res.json()
            
            if init_res.status_code != 200 or "data" not in init_data:
                err_obj = init_data.get("error", {}) if isinstance(init_data, dict) else {}
                err_code = err_obj.get("code") or "api_error"
                err_msg = err_obj.get("message") or err_code or init_res.text or "Unknown TikTok API error"
                log_id = err_obj.get("log_id", "none")
                return {"status": "error", "message": f"TikTok Init Failed [{err_code}]: {err_msg} (log_id: {log_id})"}
                
            upload_url = init_data["data"]["upload_url"]
            publish_id = init_data["data"]["publish_id"]
            
            # 2. Step 2: Binary PUT Upload (Chunked)
            with open(video_path, "rb") as f:
                for chunk_idx in range(total_chunks):
                    if chunk_idx == total_chunks - 1:
                        chunk_bytes = f.read() # Read all remaining bytes to EOF
                    else:
                        chunk_bytes = f.read(chunk_size)
                        
                    start_byte = chunk_idx * chunk_size
                    end_byte = start_byte + len(chunk_bytes) - 1
                    
                    put_headers = {
                        "Content-Type": "video/mp4",
                        "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size}"
                    }
                    
                    put_res = await client.put(upload_url, content=chunk_bytes, headers=put_headers)
                    
                    if put_res.status_code not in [200, 201, 204, 206]:
                        return {"status": "error", "message": f"TikTok Upload Chunk {chunk_idx+1}/{total_chunks} Failed ({put_res.status_code}): {put_res.text}"}
                        
            print(f"[TikTok Publisher] Success! Video uploaded in {total_chunks} chunk(s). Publish ID: {publish_id}")
            return {
                "status": "success",
                "publish_id": publish_id,
                "message": "Video successfully uploaded to TikTok Inbox Drafts!"
            }
            
        except Exception as e:
            print(f"[TikTok Publisher Error] {e}")
            return {"status": "error", "message": f"TikTok Publisher Error: {str(e)}"}
