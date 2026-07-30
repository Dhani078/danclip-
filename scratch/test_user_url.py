import asyncio
import os
import subprocess
import json
from services.ffmpeg import detect_faces_and_recommend_layout, render_viral_clip

async def main():
    url = "https://www.youtube.com/watch?v=Pf4caYt5mNc"
    print("Testing pipeline on URL:", url)
    
    temp_dir = "storage/temp"
    os.makedirs(temp_dir, exist_ok=True)
    raw_video = os.path.join(temp_dir, "test_user_video.mp4")
    
    if not os.path.exists(raw_video):
        print("Downloading sample video via yt-dlp...")
        cmd = [
            "python", "-m", "yt_dlp",
            "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", raw_video,
            "--quiet",
            "--no-warnings",
            url
        ]
        subprocess.run(cmd)
        
    print("Downloaded video exists:", os.path.exists(raw_video))
    
    # Test face detection around 02:13 (133 sec) where red car with text is!
    start_sec = 133.0
    duration_sec = 30.0
    
    face_info = detect_faces_and_recommend_layout(raw_video, start_sec, duration_sec)
    print("\n--- YuNet Analysis Result for 02:13 Car/News Segment ---")
    print(face_info)
    
    output_clip = "storage/exports/test_user_clip_133s.mp4"
    os.makedirs("storage/exports", exist_ok=True)
    
    settings = {
        "aspect_ratio": "9:16",
        "crop_style": "center_crop", # User selected center crop
        "auto_reframe": True,
        "word_karaoke": True
    }
    
    out = await render_viral_clip(raw_video, output_clip, "02:13", "02:43", subtitle_path=None, settings=settings, burn_subtitles=False)
    print("\nRendered clip path:", out)

if __name__ == "__main__":
    asyncio.run(main())
