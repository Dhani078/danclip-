# 🧠 MEMORY.md — AutoClipWeb Permanent Knowledge Base

> Dokumen ini berisi memori permanen proyek AutoClipWeb. Digunakan oleh developer dan AI assistant untuk memahami konteks, arsitektur, keputusan desain, dan parameter kritis yang telah ditetapkan.

---

## 📌 Identitas Proyek

- **Nama**: AutoClipWeb (AI Auto-Clipper Engine)
- **Versi Aktif**: v3.1.0
- **Repository**: https://github.com/Dhani078/danclip-.git (branch: `main`)
- **Stack**: Python 3.13 + FastAPI + SQLite (Async) + FFmpeg (NVENC) + Faster-Whisper (CUDA) + Gemini AI
- **Deployment**: Lokal di `c:\xampp\htdocs\autoclipweb`, diakses via `http://127.0.0.1:8000`

---

## 🤖 AI Model Fallback Chain (Gemini)

Urutan prioritas model yang digunakan di `services/gemini.py`:
```
1. gemini-3.7-flash      → Flagship SOTA, reasoning paling kuat
2. gemini-3.6-flash      → Cadangan pintar generasi 3.6
3. gemini-3.5-flash      → Cadangan pintar generasi 3.5
4. gemini-2.5-flash      → Standar stabil
5. gemini-3.5-flash-lite → Kuota besar (500 RPD), cadangan cepat
6. gemini-3.1-flash-lite → Kuota longgar (500 RPD)
7. gemini-2.0-flash      → Fallback akhir
```

---

## 🎬 Aturan Pemotongan Klip Viral (Single Micro-Story & Story Montage)

### 1. Mode Standar (Single Continuous Clip)
- **Target utama**: 30 – 45 detik (rentang: 25 – 60 detik)
- **Struktur**: 1 HOOK ➔ 1 BODY ➔ 1 PUNCHLINE dalam 1 rentang waktu utuh.
- `start_time` WAJIB dimulai dari konsonan pertama kata pembuka topik.
- `end_time` WAJIB berakhir tepat setelah titik intonasi kesimpulan.

### 2. Mode Baru: Story Montage (3-Beat Multi-Cut Narrative)
- **Fungsi**: Menggabungkan 2-3 momen terpisah dari video yang saling berkesinambungan secara logis.
- **Struktur 3-Beat Arc**:
  - *Beat 1 (Hook / Premis)*: 5–8 detik dari awal video (memicu rasa penasaran).
  - *Beat 2 (Explanation / Proof)*: 12–20 detik dari tengah video (argumen inti / data).
  - *Beat 3 (Punchline / Conclusion)*: 6–10 detik dari akhir video (solusi tuntas).
- **Multi-Cam Scale Switch**: FFmpeg otomatis merender zoom bergantian (1.0x ➔ 1.08x ➔ 1.0x) untuk efek pergantian sudut kamera studio.
- **Unified Timeline Normalization**: Whisper memetakan ulang timestamp kata-per-kata ke satu garis waktu kontinu 00:00 tanpa ada jeda subtitle.
- **Audio Acrossfade & BGM Bedding**: Audio disambung dengan 80ms crossfade dan dilapisi BGM berkesinambungan sebagai lem akustik.

---

## 🎨 Hook Header Visual (ASS Subtitle)

- **Font**: Segoe UI Black, 62pt
- **Warna**: Kuning Neon Terang (`&H0000F7FF`)
- **Outline**: 10px hitam (kontras tinggi)
- **Shadow**: 6px (efek 3D floating)
- **Background**: Plat hitam semi-transparan (`&HCC000000`)
- **Animasi**: Pop-in scale 80% → 110% → 100% (0–1.5 detik)
- **Durasi**: 0:00 – 0:04.50 (4.5 detik)
- **Posisi**: Top-center (`\an8`, MarginV=240)

---

## 🔊 Audio Pipeline

### Urutan Filter FFmpeg
```
1. silenceremove  → Hapus jeda hening di awal klip (threshold -40dB, toleransi 0.05s)
2. SFX Pop        → Delay 200ms (opsional)
3. BGM Ducking    → Sidechain compress (threshold=0.08, ratio=10)
4. loudnorm       → Normalisasi I=-16 LUFS, TP=-1.5, LRA=11
```

---

## 📱 TikTok API (Sandbox)

- **App Name**: AutoClipWeb
- **Mode**: Sandbox
- **Target User**: `lexseeme` (Display Name: Lex)
- **Client Key**: `sbawv5w4g121qq6vxm`
- **Endpoint**: TikTok Content Posting API v2

---

## 📋 SOW Default (Scope of Work Client 4Nose)

### Hashtag Wajib
```
#4nose #4noseMK #motionklip #ezklip
```

### Mention Wajib (TikTok)
```
@4noseofficial @indofragz @syaifulstayscentful @jery16_ @eddeparfum
```

---

## ⚠️ Catatan Kritis & Pelajaran

1. **Video > 20 menit** otomatis menggunakan mode Transcript Chunking (transkrip dipecah per 20K karakter).
2. **Jumlah Klip = 0 (Auto)** pada video panjang bisa menyebabkan respons JSON terpotong → gunakan angka pasti (3–5) untuk video > 20 menit.
3. **Gemini Rate Limit**: Model `gemini-2.5-flash` hanya memiliki 5 RPM pada free tier. Sistem fallback chain secara otomatis beralih ke model berikutnya jika terkena 429.
4. **NVENC Fallback**: Jika GPU gagal, sistem otomatis beralih ke `libx264 -preset veryfast -crf 21`.
5. **SQLite WAL Mode**: Database menggunakan WAL (Write-Ahead Logging) dengan `busy_timeout=30000` untuk mencegah lock saat concurrent read.

---

## 🛡️ Prinsip Pengembangan
1. **Zero-Bug Policy**: Setiap perubahan harus additive-only dan tidak boleh merusak alur yang sudah berjalan stabil.
2. **Ponytail Simplicity Ladder (Anti Over-Engineering)**:
   - *Rung 1: Does this need to exist?* → Jika tidak (YAGNI), jangan buat.
   - *Rung 2: Already in this codebase?* → Gunakan ulang, jangan buat duplikasi kode.
   - *Rung 3: Stdlib / Native Platform does it?* → Prioritaskan fitur bawaan (Python stdlib, HTML5/CSS, FFmpeg native) sebelum install package/dependency baru.
   - *Rung 4: One line?* → Buat 1 baris yang padat dan mudah dibaca.
   - *Rung 5: Minimum that works safely* → Tulis kode seminimal mungkin tanpa mengorbankan validasi, keamanan, atau error-handling.
3. **Backward Compatibility**: Semua fitur baru harus kompatibel dengan job/klip yang sudah ada di database.
4. **Graceful Degradation**: Jika fitur baru gagal (misal: model AI tidak tersedia), sistem harus fallback ke perilaku sebelumnya tanpa error.
