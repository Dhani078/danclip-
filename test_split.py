import asyncio
from services.ffmpeg import render_viral_clip

async def test():
    settings = {
        "aspect_ratio": "9:16",
        "crop_style": "center_crop",
        "auto_reframe": True,
        "layout_type": "single",
        "speaker_focus": "right",
        "bgm_ducking": False
    }
    await render_viral_clip("test2.mp4", "test_split.mp4", "00:00:05", "00:00:10", None, settings, False)

if __name__ == "__main__":
    asyncio.run(test())
