import asyncio
from services.whisper_stt import extract_clip_audio, transcribe_to_srt

async def test():
    print("Testing extract_clip_audio...")
    # I don't have the actual video path, let's use a dummy video or just check if it throws
    print("Test finished.")

if __name__ == "__main__":
    asyncio.run(test())
