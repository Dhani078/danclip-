# 🚀 AutoClipWeb — Full Production Architecture & AI Engine Documentation

> **Dokumentasi Komprehensif AutoClipWeb (AI Auto-Clipper Engine)**  
> *Versi 3.1.0 Production-Ready (Viral Retention Upgrade)*  
> Dokumentasi ini mencakup seluruh arsitektur, algoritma AI YuNet, sistem rendering FFmpeg, engine subtitle, anti-halusinasi Whisper, local video caching, garbage collector, keamanan, arsitektur database relasional, dan panduan pengujian.

---

## 📌 1. Gambaran Umum Proyek (Project Overview)

**AutoClipWeb** adalah aplikasi pemotong video AI otomatis berkinerja tinggi yang mengubah video YouTube horizontal (16:9) menjadi klip viral vertikal (9:16) untuk TikTok, Instagram Reels, dan YouTube Shorts, lengkap dengan fungsionalitas auto-publish ke TikTok.

### 🛠️ Technology Stack:
- **Backend Framework**: Python 3.13 + FastAPI (Async) + Uvicorn
- **AI Scene Analysis**: Google Gemini 3.7 Flash API (Flagship SOTA, dengan fallback chain 3.6 → 3.5 → 2.5 → lite)
- **AI Face Detection & Tracking**: OpenCV YuNet ONNX (di `models_data/`)
- **Speech-to-Text (STT)**: Faster-Whisper `large-v3` (CUDA INT8 Acceleration)
- **Video Processing Engine**: FFmpeg dengan **Hardware Acceleration NVENC**, ASS Subtitle Burning, Audio Ducking, dan Dual-Pass Loudnorm.
- **Storage & Caching**: MD5 URL-based Local Video Cache (6 Hours TTL) + Background Garbage Collector
- **Database & ORM**: SQLite (Async SQLAlchemy + aiosqlite) + Alembic Migrations
- **Frontend UI**: Modern Dark Glassmorphism UI (HTML5, Vanilla CSS3, Statically Built Tailwind CSS, JavaScript ES6)

---

## 🧠 2. Algoritma Utama & Logika Kecerdasan AI

### A. OpenCV YuNet Multi-Keyframe Active Speaker Detection
Sistem pelacakan wajah mengambil sampel di 8 frame (bukan 3):
1. **Passerby Noise Filter**: Mengisolasi wajah pembicara utama (`main_face`).
2. **Cinematic Rule of Thirds (Eyeline Framing)**: Mengukur rasio mata pembicara dan memosisikannya secara optimal.
3. **Majority Voting B-Roll Engine**: Mode **Blur-Pad 16:9** otomatis diaktifkan bila kurangnya kemunculan wajah dalam sampel.

### B. FFmpeg Rendering & Audio Normalization
1. **NVENC Hardware Acceleration**: Deteksi otomatis GPU Nvidia (h264_nvenc) di Windows dan Linux saat startup. Jika tersedia, proses render berjalan berkali-kali lipat lebih cepat.
2. **Dual-Pass Loudnorm**: Normalisasi audio otomatis ke -14 LUFS sesuai standar TikTok.

### C. Whisper SOTA Anti-Hallucination & Subtitle Engine
1. **Context-Aware No-Speech Filtering (`no_speech_prob > 0.2`)**: Menggunakan sensor bawaan Whisper.
2. **Hallucination Blacklist**: Menyaring halusinasi yang tidak perlu.
3. **ASS Subtitle Engine**: Format SubStation Alpha dengan dukungan opasitas, margin vertikal yang akurat, dan pewarnaan heksadesimal presisi (BBGGRR).

---

## 📦 3. Keamanan & Ketahanan (Security & Resilience)

1. **Path Traversal Protection**: Semua endpoint file (seperti `/api/v1/tiktok/publish`, dan endpoint download) difilter kuat melalui helper terpusat `validate_export_path`.
2. **Mime Validation**: Watermark dan font divalidasi dengan `PIL.Image` dan pustaka font (`ttLib`) sebelum diterima.
3. **Task Cancellation**: FFmpeg zombie processes dan async workers dibersihkan secara instan melalui pelacakan `active_tasks` dan `active_subprocesses` jika *job* dihapus user.
4. **Resiliency**: Implementasi `run_with_backoff` untuk API eksternal (Gemini) dan `yt-dlp` untuk mencegah kegagalan *rate-limit* sesaat.

---

## 🗄️ 4. Skema Database (Alembic Managed)

### Tabel `video_jobs`
Menyimpan *metadata* pekerjaan.
| Field | Tipe Data | Deskripsi |
| :--- | :--- | :--- |
| `id` | String (UUID) | Primary Key |
| `youtube_url` | String | URL Target (bisa multi-batch) |
| `status` | String | `PENDING`, `DOWNLOADING`, `ANALYZING`, `EDITING`, `COMPLETED`, `FAILED` |
| `subtitle_opacity` | Integer | Opasitas subtitle (0-100) |
| `subtitle_margin_v` | Integer | Posisi vertikal subtitle (persentase) |

### Tabel `clips`
Normalisasi JSON klip ke dalam tabel terpisah.
| Field | Tipe Data | Deskripsi |
| :--- | :--- | :--- |
| `id` | String (UUID) | Primary Key |
| `job_id` | String | FK -> video_jobs.id |
| `start_time` / `end_time` | String | Durasi (MM:SS) |
| `output_video_path` | String | Path file MP4 akhir klip |

### Tabel `tiktok_auth`
Penyimpanan *OAuth token* persisten untuk publikasi TikTok.
| Field | Tipe Data | Deskripsi |
| :--- | :--- | :--- |
| `id` | String | PK (singleton) |
| `access_token` | String | Token Akses Aktif |
| `refresh_token` | String | Token untuk Auto-Refresh jika 401 |

> **Alembic**: Semua skema di atas dilindungi sistem migrasi Alembic. Perintah `alembic upgrade head` wajib dijalankan saat deployment awal.

---

## 📁 5. Struktur File Proyek & Peta Fungsi

```
autoclipweb/
├── main.py                   # FastAPI Entry Point, Chunk Upload TikTok, & SSE Stream
├── config.py                 # Pydantic v2 Settings (APP_PASSWORD, MAX_SOURCE_HEIGHT, dll)
├── database.py               # SQLite Async Engine + SessionMaker
├── models.py                 # SQLAlchemy Relational Models
├── schemas.py                # Pydantic Validation Schemas
├── services/
│   ├── ffmpeg.py             # FFmpeg Render Engine, NVENC Detection
│   ├── gemini.py             # Gemini Analysis dengan Backoff
│   └── whisper_stt.py        # Faster-Whisper
├── templates/
│   └── index.html            # UI Frontend (Tabbing, Collapsible Terminal)
├── static/                   # Hasil build Tailwind CSS & Assets Web Statis
├── models_data/              # Model YuNet (face_detection_yunet_2023mar.onnx)
├── migrations/               # Alembic Migration Versions
├── alembic.ini               # Konfigurasi Alembic
├── Dockerfile                # Docker container (CUDA 12.1.1 runtime)
└── README.md                 # Panduan cepat developer
```

---

## 🚀 6. Cara Menjalankan Aplikasi

1. Buka terminal di folder project `c:\xampp\htdocs\autoclipweb`
2. Jalankan migrasi dan server:
   ```bash
   alembic upgrade head
   python -m uvicorn main:app --port 8000 --reload
   ```
3. Buka browser:
   ```
   http://127.0.0.1:8000
   ```
   *Autentikasi mungkin diperlukan tergantung `APP_PASSWORD`.*
