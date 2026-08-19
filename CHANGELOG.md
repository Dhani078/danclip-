# Changelog

Semua perubahan yang signifikan pada proyek AutoClipWeb dari Fase 1 hingga Fase 5.

## [3.0.0] - Phase 5 Refactored Release

### Fase 1: Keamanan (Security)
- **Path Traversal Protection**: Menambahkan helper `validate_export_path` di `main.py` untuk mengamankan path input klien, termasuk di endpoint `/api/v1/tiktok/publish` dan fungsi terkait I/O lainnya.
- **Mime/Magic Validation**: Menambahkan verifikasi ketat pada upload watermark dan font.
- **Task & Subprocess Cleanup**: Membersihkan proses latar belakang FFmpeg (`active_subprocesses`) jika user membatalkan pekerjaan atau menghapus job.

### Fase 2: Bug Fungsional
- **Perbaikan Skala Subtitle**: Memperbaiki pemetaan UI dari re-render ke rendering FFmpeg untuk ukuran font (70, 90, 110) sehingga tidak tiba-tiba mengecil saat user menekan "Apply & Re-Render".
- **Parameter Rendering ASS**: Menambahkan parameter `subtitle_opacity` (dengan kalkulasi ke alpha hex BBGGRR) dan nilai `margin_v` pada proses FFmpeg, sehingga modifikasi posisi dan transparansi langsung diterapkan di output klip.

### Fase 3: Kualitas Output & Performa (Optimization)
- **Sumber Resolusi Tinggi**: `yt-dlp` dimodifikasi dari target `height<=720` menjadi `height<=1080` (bisa diatur via environment `MAX_SOURCE_HEIGHT`). Ini mengatasi buram saat di-upscale ke 1080x1920 (rasio vertikal).
- **Akselerasi NVENC**: FFmpeg Service melakukan deteksi `h264_nvenc` di startup. Jika ditemukan, sistem menggunakan profil `p5` dan `tune hq` dengan bitrate dinamis untuk mengurangi waktu tunggu render hingga 400% untuk GPU Nvidia pendukung.
- **Batasan Konkurensi**: Menambahkan pembatasan pemrosesan serentak agar memory system (seperti GTX 1650 VRAM 4GB) tidak OOM (Out-of-Memory).
- **Dual-Pass Loudnorm**: FFmpeg disetel untuk merender profil audio standard TikTok `-14 LUFS` sehingga lebih konsisten.

### Fase 4: Database & Ketahanan (Reliability)
- **Integrasi Alembic**: `clipper.db` (SQLite) sekarang di-maintain oleh skema Alembic (lihat direktori `/migrations`). Perintah `create_all()` lawas diganti.
- **Skema Model Relasional**: Blob JSON untuk output video dan klip telah dinormalisasi. Skema model `Clip` diperkenalkan untuk relasi Foreign Key yang andal pada model dasar `VideoJob`.
- **TikTok Auth Tabel**: Tabel `tiktok_auth` sekarang menyimpan State, Access Token, dan Auto-refresh Token.
- **Gemini API Backoff**: Menambahkan *exponential backoff* dan implementasi retry untuk mencegah terputusnya pipa akibat batas API limit sesaat (429 Too Many Requests).

### Fase 5: UI/UX Frontend & Dokumentasi
- **Penghentian DOM Re-render**: `updateUI` tidak menimpa ulang DOM dari nol setiap ada Stream SSE datang. Pemutar video (Live Preview) tidak me-reset posisinya lagi. Render clips element hanya dilakukan SEKALI saat *state* berubah ke `COMPLETED`.
- **Static Asset Tailwind**: Pindah dari Tailwind CDN (lambat dan re-render flashing) menjadi CSS statis internal.
- **Tabbed Advanced Settings**: Form panjang pengaturan kini rapi dalam "Video & AI", "Subtitles", dan "Branding".
- **UI Terminal Lipat (Collapsible)**: Tampilan verbose backend dapat disembunyikan/di-scroll mandiri.
- **UI Notifikasi (Toasts)**: Membuang `alert()` klasik menjadi `showToast()` glassmorphism di sudut kanan bawah.
- **History Management**: User kini dapat mendelete job secara historis untuk manajemen penyimpanan yang lebih rapi.

---
*Proyek dianggap masuk tahap Release Candidate / Production-ready per versi 3.0.0 ini.*
