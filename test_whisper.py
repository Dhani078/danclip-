import asyncio
import os
from services.whisper_stt import generate_whisper_srt
from config import settings

async def main():
    temp_dir = os.path.join(settings.STORAGE_DIR, "temp")
    raw_video_path = os.path.join(temp_dir, "0955c10b-f4da-4936-b5de-fb574e2e14ae.mp4")
    
    print("Extracting audio and generating whisper SRT...")
    srt = await generate_whisper_srt(raw_video_path, "00:00", "00:30", temp_dir, "test_clip")
    print("SRT Output:")
    print(srt)

if __name__ == "__main__":
    asyncio.run(main())
