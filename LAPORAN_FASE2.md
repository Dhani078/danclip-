# LAPORAN FASE 2: VERIFIKASI & HARDENING BACKEND-FRONTEND INTEGRITY

Laporan ini menyajikan hasil akhir dari verifikasi dan perbaikan menyeluruh (hardening) untuk fase 2, yang berfokus pada integrasi struktur database baru, pengoptimalan performa video, serta ketahanan storage dan UI.

## 1. Integrasi Database Relasional & Frontend Compatibility
- **Transisi `clips_json` ke Tabel `clips`**: `clips_json` yang awalnya berupa text blob di `VideoJob` telah berhasil dipecah menjadi tabel `Clip` tersendiri. Ini memperbaiki masalah render gagal yang membuat seluruh indeks klip bergeser.
- **Frontend Backward Compatibility**: Menghindari kerusakan UI (`clipsContainer` kosong) dengan mempertahankan field `clips_json` sebagai properti dinamis (computed property) di class `VideoJob`. Properti ini secara on-the-fly memformat ulang data dari relasi `self.clips` menjadi array JSON yang persis diharapkan oleh Vanilla JS frontend:
  - Mengkonversi `start_sec` dan `end_sec` menjadi string `MM:SS` (`start_time`, `end_time`).
  - Mengembalikan `viral_score` dan `viral_reasoning`.
  - Melakukan *safe parsing* untuk field `hashtags_json` sehingga merender list `hashtags` dengan benar.
- **Alembic Migrations**: Perubahan struktur database sekarang di-manage dengan aman melalui Alembic, menghindari error "no such column".

## 2. Kualitas Output & Performa (Hardware Constraints)
- **Resolusi Source**: Konfigurasi resolusi download maksimum yt-dlp `MAX_SOURCE_HEIGHT` diatur untuk mencegah kualitas klip buram setelah di-upscale (karena 720p 9:16 hanya akan menyisakan 405x720).
- **Akselerasi NVENC (GTX 1650)**: Fallback encoder `h264_nvenc` berhasil diintegrasikan di `services/ffmpeg.py` (bersama optimasi preset `p5` dan profile `high`). CPU fallback tetap ada dengan `libx264` menggunakan parameter preset `faster` (tidak lagi `ultrafast`).
- **Penanganan Subtitle Alpha**: Logika `format(255 - round(opacity / 100 * 255), '02X')` di `whisper_stt.py` untuk ASS terverifikasi dengan benar melakukan kalkulasi transparansi (100% opacity menghasilkan alpha tag `00` atau solid, sedangkan 0% menghasilkan `FF` atau transparan penuh).

## 3. Storage & Ketahanan Sistem (Garbage Collection)
- **Pembersihan Source Maksimal**: Logika cleanup di `run_storage_cleanup` (`services/garbage_collector.py`) telah ditambahkan untuk menghapus file `storage/sources/` yang usianya melebihi `SOURCE_MAX_AGE_DAYS` (default 7 hari).
- **Manajemen Semaphore**: Limit konkurensi `asyncio.Semaphore(1)` tetap dijaga, untuk mencegah crash OOM saat task AI berat berjalan (seperti LLM reasoning atau transkripsi Whisper).

## 4. Frontend & Render UI (Bagian B)
Perbaikan krusial pada `templates/index.html`:
- **Isolasi Update SSE**: Selama processing (sebelum COMPLETED), UI hanya mengupdate komponen minor seperti progress bar dan terminal. Kartu klip kini hanya di-render penuh **satu kali** ketika status menjadi `COMPLETED`. Hal ini mencegah cache-buster dan penataan scroll hancur pada setiap tick SSE.
- **Deduplikasi Listener**: Event listener pada warna subtitle dan parameter render (re-trim/re-render) dipindahkan dari fungsi update tick, menghindari akumulasi *listener memory leak* dan duplikasi event.
- **Cleanup Kode**: Fungsi *dead code* dan cache-buster per-detik telah dihilangkan atau dioptimalkan hanya merespon parameter `updated_at`.

### Status
Sistem siap untuk diuji coba penuh (UAT: Download -> Render -> Retrim -> Load History). Tidak ada kerusakan pada alur data antara backend `Clip` dan UI Vanilla JS.
