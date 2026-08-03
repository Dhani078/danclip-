# 🚀 AutoClipWeb — Full Production Architecture & AI Engine Documentation

> **Dokumentasi Komprehensif AutoClipWeb (AI Auto-Clipper Engine)**  
> *Versi 2.1 Production-Ready (Opus Clip Pro Level Intelligence & SOTA Whisper STT)*  
> Dokumentasi ini mencakup seluruh arsitektur, algoritma AI YuNet, sistem rendering FFmpeg, engine subtitle Alex Hormozi, anti-halusinasi Whisper, local video caching, garbage collector, arsitektur database, dan panduan pengujian.

---

## 📌 1. Gambaran Umum Proyek (Project Overview)

**AutoClipWeb** adalah aplikasi pemotong video AI otomatis berkinerja tinggi yang mengubah video YouTube horizontal (16:9) menjadi klip viral vertikal (9:16) untuk TikTok, Instagram Reels, dan YouTube Shorts.

### 🛠️ Technology Stack:
- **Backend Framework**: Python 3.13 + FastAPI (Async) + Uvicorn
- **AI Scene Analysis**: Google Gemini 3.6 Flash API
- **AI Face Detection & Tracking**: OpenCV YuNet ONNX (`face_detection_yunet_2023mar.onnx`)
- **Speech-to-Text (STT)**: Faster-Whisper `large-v3` (CUDA INT8 Acceleration + SOTA Greedy Decoding)
- **Video Processing Engine**: FFmpeg (Complex Filter Graphs, ASS Subtitle Burning, Audio Ducking)
- **Storage & Caching**: MD5 URL-based Local Video Cache (6 Hours TTL) + Background Garbage Collector
- **Integration**: Telegram Bot Listener (1-Click TikTok Generator)
- **Database & ORM**: SQLite (Async SQLAlchemy) + Pydantic v2
- **Frontend UI**: Modern Dark Glassmorphism UI (HTML5, Vanilla CSS3, JavaScript ES6)

---

## 🧠 2. Algoritma Utama & Logika Kecerdasan AI

### A. OpenCV YuNet Multi-Keyframe Active Speaker Detection
Sistem pelacakan wajah menggunakan OpenCV YuNet yang mengambil sampel di **3 titik durasi klip (15%, 50%, 85%)**:
1. **Passerby Noise Filter**: Mengisolasi wajah pembicara utama (`main_face`). Wajah sekunder/latar belakang yang ukurannya $< 50\%$ dari wajah utama otomatis diabaikan.
2. **Cinematic Rule of Thirds (Eyeline Framing)**: Mengukur rasio mata pembicara (`face_center_y_ratio`) dan memosisikan level mata pada **garis 33% (1/3 atas)** dari layar vertikal 9:16.
3. **Majority Voting B-Roll Engine**: Jika minimal 2 dari 3 sampel frame sama sekali tidak memiliki wajah (misal: slide presentasi, grafik, B-Roll, atau gambar produk), sistem otomatis mengaktifkan mode **Blur-Pad 16:9** agar konten/teks tidak terpotong. Jika ada pembicara di $\ge 2$ frame, sistem **100% dijamin** menggunakan **Full 9:16 Vertical Crop**.

### B. Opus Clip Pro Level Split-Screen Engine
Untuk video podcast / wawancara 2+ orang:
1. **Wide Shot (2+ Wajah Terlihat)**: Jika Gemini menandai `layout_type == "split"` dan YuNet menemukan $\ge 2$ wajah signifikan, layar dibelah dua:
   - **Top Half**: Kamera mengunci & memosisikan **Pembicara Kiri ($X = 25\%$)** di tengah frame atas.
   - **Bottom Half**: Kamera mengunci & memosisikan **Pembicara Kanan ($X = 75\%$)** di tengah frame bawah.
2. **Camera Cut (1 Wajah Terlihat)**: Jika kamera podcast berpindah ke close-up 1 pembicara, sistem **otomatis tidak membelah layar**, melainkan beralih ke **Single Speaker Vertical Crop (1 Layar Penuh)** untuk mencegah pembicara kembar/duplikat.

### C. Whisper SOTA Anti-Hallucination & Subtitle Engine
1. **Greedy Decoding (`beam_size=1`)**: Menghilangkan fenomena *infinite looping* ("tiba-tiba...") pada model `large-v3`.
2. **Context-Aware No-Speech Filtering (`no_speech_prob > 0.2`)**: Menggunakan sensor `no_speech_prob` bawaan Whisper untuk membedakan antara *streamer yang benar-benar berbicara* dengan *halusinasi hening*.
3. **Hallucination Blacklist**: Menyaring kalimat bawaan Whisper (contoh: *"Terima kasih telah menonton"*, *"Jangan lupa subscribe"*) jika terdeteksi pada hening/musik.
4. **ASS Subtitle Engine**: Format SubStation Alpha dengan font `Segoe UI Black` + Outline 6px + Shadow 3D + *Alex Hormozi Word-by-Word Karaoke*.
5. **Viral Emoji Auto-Injection**: Otomatis menyuntikkan emoji viral berdasarkan kata kunci (contoh: `UANG` $\rightarrow$ 💰, `GILA` $\rightarrow$ 🤯, `KEREN` $\rightarrow$ 🔥, `NAIK` $\rightarrow$ 🚀, `OTAK` $\rightarrow$ 🧠, dll).

---

## 📦 3. Local Video Caching & Storage Management

1. **Persistent MD5 Cache**: Menggunakan hash MD5 dari URL YouTube untuk menyimpan video yang sudah di-download di `storage/temp/`. Jika URL sama diproses ulang dalam kurun waktu 6 jam, sistem **melewati proses re-download** dan langsung menggunakan file lokal.
2. **Automatic Storage Garbage Collector**: Layanan latar belakang (*background service*) yang berjalan setiap 1 jam sekali untuk membersihkan file ekspor dan file temporer yang usianya sudah melebihi 6 jam, menjaga ruang disk tetap efisien.

---

## 🗄️ 4. Skema Database & Data Flow

### Tabel `jobs` (SQLite):
| Field | Tipe Data | Deskripsi |
| :--- | :--- | :--- |
| `id` | String (UUID) | Primary Key pekerjaan klip |
| `youtube_url` | String | URL YouTube target |
| `status` | String | Status: `pending`, `processing`, `completed`, `failed` |
| `aspect_ratio` | String | Default: `9:16` (TikTok/Reels) |
| `subtitle_color` | String | Warna ASS Highlight (contoh: `&H00FFFF` / Yellow) |
| `subtitle_size` | Integer | Scaled font size |
| `crop_style` | String | `center_crop` atau `blur_pad` |
| `auto_reframe` | Boolean | Mengaktifkan YuNet AI Face Tracking |
| `word_karaoke` | Boolean | Mengaktifkan animasi word-by-word Alex Hormozi |
| `clips_json` | Text (JSON) | Hasil analisis AI Gemini (start_time, end_time, viral_score, caption) |
| `output_video_path` | String | Path file MP4 hasil render di `/storage/exports/` |

---

## 📁 5. Struktur File Proyek & Peta Fungsi

```
autoclipweb/
├── main.py                   # FastAPI Entry Point, Local Video Caching, & Telegram Listener
├── config.py                 # Konfigurasi aplikasi & environment variables
├── database.py               # Inisialisasi SQLAlchemy Async Engine & Session
├── models.py                 # SQLAlchemy DB Model (Job)
├── schemas.py                # Pydantic Schemas (JobCreate, JobResponse, ClipInfo)
├── services/
│   ├── ffmpeg.py             # FFmpeg Render Engine, YuNet Face Tracking, ASS Subtitle Filter
│   ├── gemini.py             # Gemini 3.6 Flash Analysis & Story Arc Clipper Prompt
│   ├── garbage_collector.py  # Storage Cleanup Service (Runs every 1 hr)
│   └── whisper_stt.py        # Faster-Whisper SOTA Transcription & ASS Generator
├── templates/
│   └── index.html            # Web Dashboard UI (Glassmorphism + Realtime Logs)
├── assets/
│   └── face_detection_yunet_2023mar.onnx # Model YuNet Face Detection
├── storage/
│   ├── temp/                 # Folder temporary cache video & audio (6 Hours TTL)
│   └── exports/              # Folder output MP4 hasil render
└── SYSTEM_DOCUMENTATION.md   # Dokumentasi Sistem Utama
```

---

## 🚀 6. Cara Menjalankan Aplikasi

1. Buka terminal di folder project `c:\xampp\htdocs\autoclipweb`:
   ```bash
   python -m uvicorn main:app --port 8000 --reload
   ```
2. Buka browser dan akses:
   ```
   http://127.0.0.1:8000
   ```
