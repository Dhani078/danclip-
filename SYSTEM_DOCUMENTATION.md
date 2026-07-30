# 🚀 AutoClipWeb — Full Production Architecture & AI Engine Documentation

> **Dokumentasi Komprehensif AutoClipWeb (AI Auto-Clipper Engine)**  
> *Versi 2.0 Production-Ready (Opus Clip Pro Level Intelligence)*  
> Dokumentasi ini mencakup seluruh arsitektur, algoritma AI YuNet, sistem rendering FFmpeg, engine subtitle Alex Hormozi, arsitektur database, dan panduan pengujian.

---

## 📌 1. Gambaran Umum Proyek (Project Overview)

**AutoClipWeb** adalah aplikasi pemotong video AI otomatis berkinerja tinggi yang mengubah video YouTube horizontal (16:9) menjadi klip viral vertikal (9:16) untuk TikTok, Instagram Reels, dan YouTube Shorts.

### 🛠️ Technology Stack:
- **Backend Framework**: Python 3.13 + FastAPI (Async) + Uvicorn
- **AI Scene Analysis**: Google Gemini 3.6 Flash API
- **AI Face Detection & Tracking**: OpenCV YuNet ONNX (`face_detection_yunet_2023mar.onnx`)
- **Speech-to-Text (STT)**: Faster-Whisper `large-v3` (CUDA INT8 Acceleration)
- **Video Processing Engine**: FFmpeg (Complex Filter Graphs, ASS Subtitle Burning, Audio Ducking)
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

### C. Subtitle Engine (Alex Hormozi Word-by-Word Karaoke)
1. **Format Subtitle**: Advanced SubStation Alpha (`.ass`).
2. **Font & Typography**: `Segoe UI Black` + Outline 6px + Shadow 3D.
3. **Dynamic Font Scaling**: Ukuran font UI ($11\text{pt} - 22\text{pt}$) otomatis di-scale ke canvas $1080 \times 1920$ ($44\text{pt} - 88\text{pt}$) agar teks tampil tebal, tegas, dan kontras tinggi di smartphone.
4. **Viral Emoji Auto-Injection**: Otomatis menyuntikkan emoji viral berdasarkan kata kunci (contoh: `UANG` $\rightarrow$ 💰, `GILA` $\rightarrow$ 🤯, `KEREN` $\rightarrow$ 🔥, `NAIK` $\rightarrow$ 🚀, `OTAK` $\rightarrow$ 🧠, dll).

---

## 🗄️ 3. Skema Database & Data Flow

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

## 📁 4. Struktur File Proyek & Peta Fungsi

```
autoclipweb/
├── main.py                   # FastAPI Entry Point & Job Queue Handler (Semaphore=1)
├── config.py                 # Konfigurasi aplikasi & environment variables
├── database.py               # Inisialisasi SQLAlchemy Async Engine & Session
├── models.py                 # SQLAlchemy DB Model (Job)
├── schemas.py                # Pydantic Schemas (JobCreate, JobResponse, ClipInfo)
├── services/
│   ├── ffmpeg.py             # FFmpeg Render Engine, YuNet Face Tracking, ASS Subtitle Filter
│   ├── gemini.py             # Gemini 3.6 Flash Analysis & Story Arc Clipper Prompt
│   └── whisper_stt.py        # Faster-Whisper Transcription & ASS Generator
├── templates/
│   └── index.html            # Web Dashboard UI (Glassmorphism + Realtime Logs)
├── assets/
│   └── face_detection_yunet_2023mar.onnx # Model YuNet Face Detection
├── storage/
│   ├── temp/                 # Folder temporary download & audio
│   └── exports/              # Folder output MP4 hasil render
└── SYSTEM_DOCUMENTATION.md   # Dokumentasi Sistem Utama
```

---

## 🧪 5. Panduan Pengujian & Verifikasi (Test Suite)

Project ini dilengkapi dengan **2 script pengujian mandiri**:

### 1. Test Rendering & YuNet Face Tracking (`test_render.py`)
Memvalidasi deteksi wajah YuNet, framing Rule of Thirds, dan kompilasi filter complex FFmpeg:
```bash
python C:\Users\Anomali\.gemini\antigravity\brain\1e2ceb93-a1d2-4e2a-8632-c9941e9c2778\scratch\test_render.py
```

### 2. Test Integration API FastAPI (`test_api.py`)
Memvalidasi endpoint API (`/`, `/favicon.ico`, `/api/v1/clips/history`, dan `POST /api/v1/clips`):
```bash
python C:\Users\Anomali\.gemini\antigravity\brain\1e2ceb93-a1d2-4e2a-8632-c9941e9c2778\scratch\test_api.py
```

---

## 🚀 6. Cara Menjalankan Aplikasi

1. Buka terminal di folder project `c:\xampp\htdocs\autoclipweb`:
   ```bash
   python main.py
   ```
2. Buka browser dan akses:
   ```
   http://127.0.0.1:8080
   ```

---
*Dokumentasi ini dibuat untuk memastikan seluruh konteks teknis arsitektur AutoClipWeb tersimpan dengan sempurna.*
