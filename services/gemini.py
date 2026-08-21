import os
import json
import asyncio
from google import genai
from google.genai import types
from config import settings
from schemas import GeminiAnalysisSchema

VIRALITY_CRITERIA = """
🔥 KRITERIA SINYAL VIRAL (WAJIB DIPRIORITASKAN):
1. HOOK MOMENTS — Pernyataan yang langsung memicu rasa ingin tahu di 3 detik pertama ("Rahasia terbesarnya adalah...", "Semua orang salah tentang...").
2. EMOTIONAL PEAKS — Reaksi emosional yang intens (tawa lepas, amarah, kejutan, atau kerentanan asli).
3. OPINION BOMBS — Opini berani, kontroversial, atau berlawanan dengan arus utama yang memancing perdebatan di kolom komentar.
4. REVELATION MOMENTS — Fakta, statistik, atau pengakuan mengejutkan yang mengubah perspektif penonton (*mind-blowing*).
5. CONFLICT/TENSION — Ketegangan, ketidaksetujuan, atau argumen tajam antar pembicara.
6. QUOTABLE ONE-LINERS — Kutipan tajam satu kalimat yang sangat *relatable* dan mudah dibagikan.
7. STORY PEAKS — Puncak atau *plot twist* dari sebuah cerita/anekdot.
8. PRACTICAL VALUE — Tips atau ilmu "daging" yang sangat praktis dan bisa langsung diterapkan penonton.
"""

def dedupe_highlights(clips: list) -> list:
    """Drop a clip if it overlaps >50% with a higher-scoring one already kept."""
    def parse_time(ts_str):
        parts = str(ts_str).strip().split(':')
        try:
            if len(parts) == 2: return int(parts[0]) * 60 + int(parts[1])
            if len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            return float(ts_str)
        except (ValueError, TypeError, IndexError):
            return 0
            
    clips = sorted(clips, key=lambda x: x.viral_score, reverse=True)
    kept = []
    for h in clips:
        h_start = parse_time(h.start_time)
        h_end = parse_time(h.end_time)
        h_dur = h_end - h_start
        if h_dur <= 0: continue
        
        overlapping = False
        for k in kept:
            k_start = parse_time(k.start_time)
            k_end = parse_time(k.end_time)
            latest_start = max(h_start, k_start)
            earliest_end = min(h_end, k_end)
            overlap = earliest_end - latest_start
            if overlap > 0 and overlap > 0.5 * h_dur:
                overlapping = True
                break
        if not overlapping:
            kept.append(h)
    return kept

def sanitize_hashtags(tag_list: list, default_tags: list) -> list:
    """Clean and enforce exactly 5 formatted hashtags."""
    cleaned = []
    if tag_list:
        for t in tag_list:
            if not isinstance(t, str):
                continue
            t_clean = t.strip()
            if not t_clean:
                continue
            if not t_clean.startswith("#"):
                t_clean = f"#{t_clean}"
            if t_clean not in cleaned:
                cleaned.append(t_clean)
    
    # Fill up to 5 with default tags if needed
    for dt in default_tags:
        if len(cleaned) >= 5:
            break
        if dt not in cleaned:
            cleaned.append(dt)
            
    return cleaned[:5]

async def analyze_video(video_path: str, custom_prompt: str = "", clip_count: int = 3, custom_api_key: str = "", target_keyword: str = "", target_start_time: str = "", target_end_time: str = "") -> GeminiAnalysisSchema:
    api_key = custom_api_key.strip() if custom_api_key and custom_api_key.strip() else settings.GEMINI_API_KEY
    if not api_key:
        raise Exception("GEMINI_API_KEY is missing. Please set it in .env or provide your custom API Key.")
        
    client = genai.Client(api_key=api_key)
    
    """Uploads video to Gemini and analyzes it for viral potential."""
    try:
        uploaded_file = await client.aio.files.upload(file=video_path)
        
        max_wait = 60  # max ~120 seconds
        wait_count = 0
        while True:
            file_info = await client.aio.files.get(name=uploaded_file.name)
            state = file_info.state
            state_name = getattr(state, "name", state)
            if state_name == "ACTIVE":
                break
            elif state_name == "FAILED":
                raise Exception("File processing failed on Gemini.")
            wait_count += 1
            if wait_count >= max_wait:
                raise Exception("Gemini file processing timed out after 120 seconds.")
            await asyncio.sleep(2)

        user_instruction = ""
        if custom_prompt:
            user_instruction = (
                f"🚨 SOW / MASTER DIRECTOR BRIEF (SANGAT KRITIS): 🚨\n"
                f"Pengguna telah memberikan instruksi / SOW (Scope of Work) spesifik berikut:\n"
                f"\"\"\"\n{custom_prompt}\n\"\"\"\n"
                f"PERINTAH MUTLAK: Anda WAJIB patuh pada SEMUA aturan, larangan, dan panduan di dalam SOW di atas. SOW ini adalah panduan tertinggi Anda. Jika ada instruksi yang melarang sesuatu (misal: dilarang menyebut merk kompetitor), Anda harus memastikannya.\n\n"
            )

        keyword_instruction = (
            f"🛒🎯 TARGET KEYWORD / AFFILIATE WAJIB PRIORITAS: '{target_keyword}'\n"
            f"FOKUS UTAMA: Anda DITUNTUT secara MUTLAK untuk mencari momen di mana subjek membahas, menyebutkan, menampilkan, atau mereview hal yang relevan dengan '{target_keyword}'. "
            f"Pastikan klip yang diekstrak menonjolkan poin penjualan (selling point) atau emosi dari topik ini untuk keperluan afiliasi!\n\n"
        ) if target_keyword else ""

        time_constraint_instruction = ""
        if target_start_time and target_end_time:
            time_constraint_instruction = (
                f"⏱️ BATASAN WAKTU MUTLAK (ANTI-HALUSINASI):\n"
                f"Pengguna telah menandai bahwa momen yang dicari berada TEPAT di rentang waktu {target_start_time} hingga {target_end_time}.\n"
                f"Anda DILARANG KERAS mengekstrak klip di luar rentang waktu ini. Analisis secara mendalam percakapan HANYA di dalam jendela waktu tersebut, dan temukan detik yang paling sempurna. "
                f"Jika tidak ada kecocokan sama sekali di dalam rentang waktu ini, kembalikan JSON klip kosong `[]`, jangan mengarang waktu lain!\n\n"
            )

        clip_count_instruction = f"Tugas Anda adalah mengekstrak SEBANYAK MUNGKIN klip momen TERBAIK & PALING POTENSIAL VIRAL dari video ini.\n\n" if clip_count == 0 else f"Tugas Anda adalah mengekstrak {clip_count} klip momen TERBAIK & PALING POTENSIAL VIRAL dari video ini.\n\n"
        prompt = (
            f"Bertindaklah sebagai Chief Content Officer, Master Viral Strategist, & Lead Editor untuk Short-Form Video (TikTok, IG Reels, YouTube Shorts).\n"
            f"{clip_count_instruction}"
            f"{user_instruction}"
            f"{keyword_instruction}"
            f"{time_constraint_instruction}"
            f"{VIRALITY_CRITERIA}\n"
            f"📌 PEDOMAN EKSTRAKSI MASTERCLASS (STRICT COMPLETE-TOPIC RULES):\n"
            f"1. TIMESTAMP ACCURACY: Gunakan TIMESTAMP HANYA dari waktu asli yang terdapat pada media video. DILARANG MEMBUAT TIMESTAMP FIKTIF!\n"
            f"2. DURASI UTUH & CONTEXT RETENTION (30 DETIK - 3 MENIT): DILARANG KERAS membuat klip singkat 10-15 detik yang memotong gagasan! Durasi ideal klip adalah 30 detik hingga 180 detik (1-3 menit) agar alur topik, argumen, dan kesimpulan dapat tersampaikan secara tuntas & memikat.\n"
            f"3. DILARANG TERPOTONG DI TENGAH KALIMAT (NO MID-SENTENCE CUTS): `start_time` WAJIB dimulai dari awal kata/pertanyaan pertama suatu topik. `end_time` WAJIB berakhir tepat setelah pembicara menyelesaikan titik poin kesimpulannya secara sempurna.\n"
            f"4. HOOK TITLE FORMAT: `hook_title` WAJIB berupa 3-5 KATA KAPITAL SERU & PROVOKATIF yang dilengkapi 1 Emoji menarik (Contoh: 'JANGAN SALAH STRATEGI! 😱').\n"
            f"5. HASHTAG STANDARIZATION: Setiap klip WAJIB memiliki TEPAT 5 HASHTAG (minimal 5, maksimal 5) yang relevan untuk masing-masing platform.\n"
            f"6. DISTRIBUSI KONTEN: Jika video berdurasi panjang, ratakan ekstraksi klip dari awal, tengah, hingga akhir video.\n\n"
            f"📌 CONTOH EKSTRAKSI STANDAR EMAS (GOLD-STANDARD EXEMPLAR):\n"
            f"- START TIME: 01:14 (Mulai tepat saat pembicara memicu pertanyaan/gagasan baru)\n"
            f"- END TIME: 02:45 (Berakhir tepat saat pembicara menutup poin pemikiran secara tuntas)\n"
            f"- HOOK TITLE: 'RAHASIA TERSEMBUNYI! 🔥'\n"
            f"- VIRAL REASONING: 'Membuka Curiosity Gap kuat di 5 detik pertama. Pembicara membeberkan solusi konkret dengan retensi tinggi hingga detik ke-165 tanpa potongan kalimat menggantung.'\n\n"
            f"📌 DETAIL OUTPUT PER KLIP:\n"
            f"- `viral_score`: Nilai potensi viral 1-100.\n"
            f"- `viral_reasoning`: Penjelasan logis 2-3 kalimat mengapa klip ini memicu retensi penonton tinggi.\n"
            f"- `hook_title`: Header 3-5 kata seru & provokatif yang dipasang di atas klip.\n"
            f"- `tiktok_titles`: 3 variasi judul unik bergaya click-trigger khas TikTok.\n"
            f"- `reels_titles`: 3 variasi judul unik bergaya estetis & naratif khas Reels.\n"
            f"- `shorts_titles`: 3 variasi judul unik bergaya tajam & to-the-point khas Shorts.\n"
            f"- `hashtags`: TEPAT 5 hashtag umum relevan.\n"
            f"- `tiktok_hashtags`: TEPAT 5 hashtag spesifik algoritma TikTok.\n"
            f"- `reels_hashtags`: TEPAT 5 hashtag spesifik algoritma Instagram Reels.\n"
            f"- `shorts_hashtags`: TEPAT 5 hashtag spesifik algoritma YouTube Shorts.\n"
            f"- `tiktok_caption`, `reels_caption`, `shorts_caption`: Caption tersesuaikan dengan karakteristik masing-masing platform.\n\n"
            f"Kembalikan respon murni JSON sesuai schema."
        )

        models_to_try = [
            'gemini-3.7-flash',
            'gemini-3.6-flash',
            'gemini-3.5-flash',
            'gemini-2.5-flash',
            'gemini-3.5-flash-lite',
            'gemini-3.1-flash-lite',
            'gemini-2.0-flash'
        ]
        
        response = None
        last_error = None
        
        for model_name in models_to_try:
            try:
                print(f"[Gemini] Attempting analysis with model: {model_name}")
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=[uploaded_file, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=GeminiAnalysisSchema,
                        temperature=0.3,
                        max_output_tokens=8192,
                        safety_settings=[
                            types.SafetySetting(
                                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                            ),
                            types.SafetySetting(
                                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                            ),
                            types.SafetySetting(
                                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                            ),
                            types.SafetySetting(
                                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                            ),
                        ]
                    ),
                )
                print(f"[Gemini] Successfully analyzed with {model_name}")
                break
            except Exception as e:
                print(f"[Gemini] Warning: {model_name} failed ({str(e)}). Switching to next model...")
                last_error = e
                await asyncio.sleep(2)
                continue
                    
        if not response:
            raise Exception(f"All Gemini models exhausted their quota limits! Last error: {last_error}")
        
        await client.aio.files.delete(name=uploaded_file.name)
        
        text = response.text if hasattr(response, 'text') and response.text else ""
        if not text:
            raise Exception("network error: Gemini returned empty response (possibly blocked by safety filters or rate limit).")
            
        import re
        match = re.search(r"```(?:json)?(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if match:
            text = match.group(1).strip()
            
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"[Gemini] JSON Decode Error: {e}. Attempting manual recovery of partial JSON...")
            fixed = False
            temp_text = text
            while temp_text:
                last_brace = temp_text.rfind('}')
                if last_brace == -1:
                    break
                temp_text = temp_text[:last_brace+1]
                # Try appending standard closing brackets for our schema
                try:
                    data = json.loads(temp_text + "\n]}")
                    fixed = True
                    print("[Gemini] Successfully recovered partial JSON clips!")
                    break
                except:
                    # Try just } if it wasn't inside the array yet
                    try:
                        data = json.loads(temp_text)
                        fixed = True
                        break
                    except:
                        temp_text = temp_text[:-1]
            if not fixed:
                print(f"\n[DEBUG] Raw Truncated Text from Gemini:\n{text}\n")
                raise Exception(f"network error: Failed to recover truncated JSON (too short): {str(e)}")
            
        schema_obj = GeminiAnalysisSchema(**data)
        
        # Apply anti-duplicate overlap filter
        schema_obj.clips = dedupe_highlights(schema_obj.clips)
        
        # Post-process & strict normalization on hashtags and titles
        default_tt = ["#fyp", "#viral", "#foryoupage", "#trending", "#shorts"]
        default_reels = ["#reels", "#explore", "#viral", "#trending", "#instagram"]
        default_shorts = ["#shorts", "#trending", "#viral", "#youtube", "#shortsvideo"]
        default_gen = ["#fyp", "#viral", "#trending", "#shorts", "#reels"]

        for c in schema_obj.clips:
            c.tiktok_hashtags = sanitize_hashtags(getattr(c, 'tiktok_hashtags', []), default_tt)
            c.reels_hashtags = sanitize_hashtags(getattr(c, 'reels_hashtags', []), default_reels)
            c.shorts_hashtags = sanitize_hashtags(getattr(c, 'shorts_hashtags', []), default_shorts)
            c.hashtags = sanitize_hashtags(getattr(c, 'hashtags', []), default_gen)

            # Ensure non-empty titles lists
            if not c.tiktok_titles or len(c.tiktok_titles) == 0:
                c.tiktok_titles = [c.hook_title or "Viral Clip", "Nonton Sampai Habis! 😱", "Wajib Tahu Ini! 🔥"]
            if not c.reels_titles or len(c.reels_titles) == 0:
                c.reels_titles = [c.hook_title or "Viral Moment", "Spill Rahasianya ✨", "Save & Share Momen Ini! 📌"]
            if not c.shorts_titles or len(c.shorts_titles) == 0:
                c.shorts_titles = [c.hook_title or "Shorts Highlight", "Momen Langka! ⚡", "Topik Menarik Hari Ini 💡"]

        return schema_obj
    except Exception as e:
        raise Exception(f"Gemini API Error: {str(e)}")

async def analyze_transcript_chunks(transcript_text: str, custom_prompt: str = "", clip_count: int = 3, custom_api_key: str = "") -> GeminiAnalysisSchema:
    api_key = custom_api_key.strip() if custom_api_key and custom_api_key.strip() else settings.GEMINI_API_KEY
    if not api_key:
        raise Exception("GEMINI_API_KEY is missing. Please set it in .env or provide your custom API Key.")
        
    client = genai.Client(api_key=api_key)
    
    CHUNK_SIZE = 20000
    OVERLAP = 500
    
    chunks = []
    start = 0
    
    while start < len(transcript_text):
        end = start + CHUNK_SIZE
        if end >= len(transcript_text):
            chunks.append(transcript_text[start:])
            break
            
        # Cari newline atau spasi terakhir sebelum batas potongan agar tidak memotong kata di tengah
        last_break = transcript_text.rfind('\n', start, end)
        if last_break == -1 or last_break <= start:
            last_break = transcript_text.rfind(' ', start, end)
            
        if last_break != -1 and last_break > start:
            end = last_break
            
        chunks.append(transcript_text[start:end])
        
        # Hitung overlap dengan mencari batas kata/kalimat terdekat
        start = end - OVERLAP
        if start > 0:
            first_break = transcript_text.find('\n', start, end)
            if first_break == -1 or first_break >= end:
                first_break = transcript_text.find(' ', start, end)
            if first_break != -1 and first_break < end:
                start = first_break + 1
        else:
            start = end
        
    all_clips = []
    
    models_to_try = [
        'gemini-3.7-flash',
        'gemini-3.6-flash',
        'gemini-3.5-flash',
        'gemini-2.5-flash',
        'gemini-3.5-flash-lite',
        'gemini-3.1-flash-lite',
        'gemini-2.0-flash'
    ]
    
    for i, chunk_text in enumerate(chunks):
        user_instruction = (
            f"🎯 PRIORITAS UTAMA PENGGUNA (CUSTOM REQUEST):\n"
            f"'{custom_prompt}'\n\n"
        ) if custom_prompt else ""

        clip_count_instruction = f"Tugas Anda mengekstrak SEBANYAK MUNGKIN klip momen TERBAIK dari bagian transkrip ini.\n\n" if clip_count == 0 else f"Tugas Anda mengekstrak hingga {clip_count} klip momen TERBAIK dari bagian transkrip ini.\n\n"
        prompt = (
            f"Bertindaklah sebagai Chief Content Officer & Master Viral Strategist.\n"
            f"Ini adalah BAGIAN {i+1} dari {len(chunks)} dari sebuah transkrip video panjang.\n"
            f"{clip_count_instruction}"
            f"{user_instruction}"
            f"{VIRALITY_CRITERIA}\n"
            f"📌 PEDOMAN EKSTRAKSI MASTERCLASS (STRICT COMPLETE-TOPIC RULES):\n"
            f"1. DURASI UTUH & CONTEXT RETENTION (30 DETIK - 3 MENIT): DILARANG KERAS membuat klip singkat 10-15 detik yang memotong gagasan! Durasi ideal klip adalah 30 detik hingga 180 detik (1-3 menit) agar alur topik, argumen, dan kesimpulan dapat tersampaikan secara tuntas & memikat.\n"
            f"2. DILARANG TERPOTONG DI TENGAH KALIMAT (NO MID-SENTENCE CUTS): `start_time` WAJIB dimulai dari awal kata/pertanyaan pertama suatu topik. `end_time` WAJIB berakhir tepat setelah pembicara menyelesaikan titik poin kesimpulannya secara sempurna. Jangan dibulatkan secara sembarangan!\n"
            f"3. HOOK TITLE FORMAT: `hook_title` WAJIB berupa 3-5 KATA KAPITAL SERU & PROVOKATIF yang dilengkapi 1 Emoji menarik (Contoh: 'FAKTA MENGEJUTKAN! 😱').\n"
            f"4. TIMESTAMP ACCURACY: Gunakan persis timestamp yang tertera pada transkrip ini.\n\n"
            f"📌 CONTOH EKSTRAKSI STANDAR EMAS (GOLD-STANDARD EXEMPLAR):\n"
            f"- START TIME: 01:14 (Mulai tepat saat pembicara memicu gagasan/pertanyaan baru)\n"
            f"- END TIME: 02:45 (Berakhir tepat saat pembicara menutup poin pemikiran secara tuntas)\n"
            f"- HOOK TITLE: 'RAHASIA TERSEMBUNYI! 🔥'\n"
            f"- VIRAL REASONING: 'Membuka Curiosity Gap kuat di 5 detik pertama. Pembicara membeberkan solusi konkret dengan retensi tinggi hingga detik ke-165 tanpa potongan kalimat menggantung.'\n\n"
            f"Transkrip:\n{chunk_text}\n\n"
            f"Kembalikan respon murni JSON sesuai schema GeminiAnalysisSchema."
        )

        response = None
        for model_name in models_to_try:
            try:
                print(f"[Gemini Chunk {i+1}] Attempting with {model_name}")
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=GeminiAnalysisSchema,
                        temperature=0.3,
                        max_output_tokens=8192,
                        safety_settings=[
                            types.SafetySetting(
                                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                            ),
                            types.SafetySetting(
                                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                            ),
                            types.SafetySetting(
                                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                            ),
                            types.SafetySetting(
                                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                            ),
                        ]
                    ),
                )
                break
            except Exception as e:
                print(f"[Gemini Chunk {i+1}] Warning: {model_name} failed with error: {str(e)}. Moving to next...")
                await asyncio.sleep(2)
                continue
                
        if response and hasattr(response, 'text') and response.text:
            text = response.text
            import re
            match = re.search(r"```(?:json)?(.*?)```", text, re.DOTALL | re.IGNORECASE)
            if match: text = match.group(1).strip()
            
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                print(f"[Gemini Chunk {i+1}] JSON Decode Error: {e}. Attempting manual recovery of partial JSON...")
                fixed = False
                temp_text = text
                while temp_text:
                    last_brace = temp_text.rfind('}')
                    if last_brace == -1:
                        break
                    temp_text = temp_text[:last_brace+1]
                    try:
                        data = json.loads(temp_text + "\n]}")
                        fixed = True
                        break
                    except:
                        try:
                            data = json.loads(temp_text)
                            fixed = True
                            break
                        except:
                            temp_text = temp_text[:-1]
                if not fixed:
                    print(f"[Gemini Chunk {i+1}] network error: Failed to recover truncated JSON. Skipping chunk.")
                    continue
                    
            try:
                schema_obj = GeminiAnalysisSchema(**data)
                all_clips.extend(schema_obj.clips)
            except Exception as e:
                print(f"[Gemini Chunk {i+1}] Failed to parse Pydantic schema: {e}")
                
    # Filter and dedupe
    all_clips = dedupe_highlights(all_clips)
    all_clips = sorted(all_clips, key=lambda x: x.viral_score, reverse=True)
    if clip_count > 0:
        all_clips = all_clips[:clip_count]
    
    final_schema = GeminiAnalysisSchema(clips=all_clips)
    
    default_tt = ["#fyp", "#viral", "#foryoupage", "#trending", "#shorts"]
    default_reels = ["#reels", "#explore", "#viral", "#trending", "#instagram"]
    default_shorts = ["#shorts", "#trending", "#viral", "#youtube", "#shortsvideo"]
    default_gen = ["#fyp", "#viral", "#trending", "#shorts", "#reels"]

    for c in final_schema.clips:
        c.tiktok_hashtags = sanitize_hashtags(getattr(c, 'tiktok_hashtags', []), default_tt)
        c.reels_hashtags = sanitize_hashtags(getattr(c, 'reels_hashtags', []), default_reels)
        c.shorts_hashtags = sanitize_hashtags(getattr(c, 'shorts_hashtags', []), default_shorts)
        c.hashtags = sanitize_hashtags(getattr(c, 'hashtags', []), default_gen)

        if not c.tiktok_titles or len(c.tiktok_titles) == 0:
            c.tiktok_titles = [c.hook_title or "Viral Clip", "Nonton Sampai Habis! 😱", "Wajib Tahu Ini! 🔥"]
        if not c.reels_titles or len(c.reels_titles) == 0:
            c.reels_titles = [c.hook_title or "Viral Moment", "Spill Rahasianya ✨", "Save & Share Momen Ini! 📌"]
        if not c.shorts_titles or len(c.shorts_titles) == 0:
            c.shorts_titles = [c.hook_title or "Shorts Highlight", "Momen Langka! ⚡", "Topik Menarik Hari Ini 💡"]

    return final_schema
