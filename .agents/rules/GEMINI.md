# AutoClipWeb — Workspace Rules

## Bahasa & Komunikasi
- Gunakan **Bahasa Indonesia** untuk semua komunikasi dengan user.
- Komentar kode boleh dalam Bahasa Inggris atau Indonesia.

## Prinsip Kode
- **Zero-Bug Policy**: Setiap perubahan WAJIB bersifat additive-only. DILARANG merusak alur yang sudah berjalan stabil.
- **No Breaking Changes**: Semua fitur baru harus backward-compatible dengan job/klip yang sudah ada di database.
- **Graceful Degradation**: Jika fitur baru gagal, sistem HARUS fallback ke perilaku sebelumnya tanpa crash.
- **Test Before Commit**: Selalu jalankan `python -c "import services.gemini; import services.whisper_stt; import services.ffmpeg; print('OK')"` sebelum commit.

## Arsitektur
- Backend: Python 3.13 + FastAPI (Async) + Uvicorn
- Database: SQLite (Async SQLAlchemy + aiosqlite) + Alembic
- AI: Google Gemini API (fallback chain: 3.7-flash → 3.6 → 3.5 → 2.5 → lite models)
- Video: FFmpeg dengan NVENC GPU acceleration + libx264 CPU fallback
- STT: Faster-Whisper large-v3-turbo (CUDA)
- Frontend: Vanilla HTML/CSS/JS (dark glassmorphism)

## File Penting
- `MEMORY.md` — Memori permanen proyek (arsitektur, parameter, keputusan)
- `SYSTEM_DOCUMENTATION.md` — Dokumentasi teknis lengkap
- `CHANGELOG.md` — Riwayat perubahan per versi
- `.env` — Kredensial (JANGAN pernah commit ke git)

## Konvensi
- Semua path file di Windows menggunakan backslash (`\`) kecuali di dalam FFmpeg filter graph (gunakan forward slash `/`).
- Semua timestamp klip menggunakan format `MM:SS` atau `HH:MM:SS`.
- Subtitle menggunakan format ASS (SubStation Alpha) dengan resolusi PlayRes 1080x1920.
