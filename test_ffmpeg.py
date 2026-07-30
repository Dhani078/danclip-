import asyncio
import os
from services.ffmpeg import render_viral_clip

async def test():
    # Make a 5-second test video with all settings
    print("Testing ffmpeg render_viral_clip...")
    settings = {
        "aspect_ratio": "9:16",
        "crop_style": "center_crop",
        "auto_reframe": True,
        "bgm_ducking": False
    }
    
    input_vid = "test2.mp4"
    if not os.path.exists(input_vid):
        print(f"Skipping test: {input_vid} not found.")
        return
        
    try:
        await render_viral_clip(
            input_path=input_vid,
            output_path="test_out.mp4",
            start_time="00:00:05",
            end_time="00:00:10",
            subtitle_path=None,
            settings=settings,
            burn_subtitles=False
        )
        print("Render Success!")
    except Exception as e:
        print(f"Render Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
