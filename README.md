# AutoClipWeb

AutoClipWeb is an automated AI-powered video clipping engine. It transforms horizontal YouTube videos (16:9) into viral vertical clips (9:16) for TikTok, Reels, and Shorts.

It leverages OpenCV (YuNet) for intelligent speaker tracking, Faster-Whisper for high-quality SubStation Alpha (ASS) subtitles, and Gemini Flash 3.6 for analyzing and selecting the most engaging, viral moments.

## Phase 5 (Version 3.0) Features
- **Frontend Performance**: Statically built Tailwind CSS and highly optimized vanilla JS DOM updates.
- **Relational DB**: SQLite with SQLAlchemy Async, segmented models (VideoJobs, Clips), managed via Alembic.
- **Hardware Acceleration**: Automatic NVENC encoding fallback, substantially speeding up FFmpeg render times on supported GPUs.
- **TikTok Integration**: Secure, robust OAuth pipeline with auto token-refresh mechanism for direct application-to-TikTok publishing.
- **Security & Stability**: Strong file path traversal defenses (`validate_export_path`) and active task cancellation/garbage collection.

## Installation & Setup

1. **Prerequisites**
   - Python 3.13
   - FFmpeg installed and accessible in your system `PATH`.
   - SQLite



3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Database Migration**
   Initialize the database to the latest schema using Alembic:
   ```bash
   alembic upgrade head
   ```

5. **Run the Application**
   ```bash
   python -m uvicorn main:app --port 8000 --reload
   ```
   Access the web interface at `http://127.0.0.1:8000/`.

## Documentation
For deep technical insight into the AI algorithms (Rule of Thirds framing, Hallucination-filtering, Garbage collection), refer to `SYSTEM_DOCUMENTATION.md`.

## Docker
A `Dockerfile` is provided for running the service in an isolated environment with pre-configured dependencies, especially useful for ensuring consistent FFmpeg and CUDA (if configured) support across Windows and Linux hosts.
