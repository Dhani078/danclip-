import os
from google import genai
from google.genai import types
from config import settings
from schemas import GeminiAnalysisSchema
import json
import asyncio

async def analyze_video(video_path: str, custom_prompt: str = "", clip_count: int = 3, custom_api_key: str = "") -> GeminiAnalysisSchema:
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

        user_instruction = f" Arahan Tambahan Pengguna: {custom_prompt}\n" if custom_prompt else ""

        prompt = (
            f"Bertindaklah sebagai Senior Content Strategist & Viral TikTok Copywriter.\n"
            f"Analisis isi konten video/podcast ini dan ekstrak {clip_count} momen TERBAIK yang paling berpotensi FYP & VIRAL.\n\n"
            f"{user_instruction}"
            f"🎯 ADAPTASI TOPIK & GAYA BAHASA (WAJIB DYNAMIC, SANTAI & SANGAT RELATABLE):\n"
            f"- ADAPTASI 100% SESUAI KONTEN VIDEO! Identifikasi topik utama (bisnis, agama, edukasi, hiburan, teknologi, percintaan, karir, dll.) dan sebutkan nama pembicara jika ada.\n"
            f"- `viral_reasoning`: Berikan alasan detail 2-3 kalimat MENGAPA klip ini bernilai viral (contoh: 'Klip ini memiliki viral score 95/100 karena membuka dengan pertanyaan provokatif di 3 detik pertama dan membawa emosi retensi tinggi tentang topik X.').\n"
            f"- JANGAN GUNAKAN BAHASA BAKU/FORMAL SEPERTI MAKALAH ATAU BERITA RESMI!\n"
            f"- Gunakan bahasa gaul/populer anak muda TikTok yang sesuai dengan topik video tersebut.\n"
            f"- `hook_title`: Buat 3-5 kata HOOK UTAMA yang SANGAT PROVOKATIF & MEMANCING PENASARAN.\n"
            f"- `tiktok_titles`: Buat 3 VARIASI JUDUL UNIK khusus algoritma TikTok (gaya memancing rasa penasaran / klik).\n"
            f"- `reels_titles`: Buat 3 VARIASI JUDUL UNIK khusus algoritma Instagram Reels (gaya estetis / storytelling).\n"
            f"- `shorts_titles`: Buat 3 VARIASI JUDUL UNIK khusus algoritma YouTube Shorts (gaya to-the-point & tajam).\n"
            f"- `tiktok_hashtags`: List 5+ hashtag spesifik TikTok (#fyp #viral + hashtag topik).\n"
            f"- `reels_hashtags`: List 5+ hashtag spesifik Instagram Reels (#reels #explore + hashtag topik).\n"
            f"- `shorts_hashtags`: List 5+ hashtag spesifik YouTube Shorts (#shorts #trending + hashtag topik).\n"
            f"- `tiktok_caption`: Buat caption khas TikToker pro yang interaktif dengan hook emosional & pertanyaan pemicu komentar.\n"
            f"- `reels_caption`: Caption Instagram Reels (estetis, naratif bercerita, paragraf rapi & hashtag relevan).\n"
            f"- `shorts_caption`: Caption YouTube Shorts (singkat, padat, gaya judul tajam & #shorts).\n\n"
            f"⏱️ ATURAN TIMESTAMP & STRUKTUR:\n"
            f"- Gunakan timestamp ASLI dari video. Jangan reset ke 00:00:00.\n"
            f"- Durasi Bebas (bisa 30 detik hingga 2+ menit) asal pembicaraannya padat 'daging' dan tidak terpotong pertengahan kalimat!\n\n"
            f"📐 LAYOUT VISUAL:\n"
            f"- `layout_type`: 'single' jika 1 pembicara utama, 'split' jika interaksi 2 pembicara (tanya-jawab).\n"
            f"- `speaker_focus`: 'left', 'center', atau 'right'.\n\n"
            f"Kembalikan respon murni dalam format JSON sesuai schema."
        )
        
        models_to_try = [
            'gemini-3.6-flash',
            'gemini-3.5-flash',
            'gemini-3.1-pro',
            'gemini-3.1-flash-lite',
            'gemini-3-flash',
            'gemini-2.5-pro',
            'gemini-2.5-flash',
            'gemini-2.5-flash-lite',
            'gemini-2-flash'
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
                        temperature=0.4,
                    ),
                )
                print(f"[Gemini] Successfully analyzed with {model_name}")
                break
            except Exception as e:
                error_str = str(e).lower()
                if any(k in error_str for k in ["429", "503", "exhausted", "quota", "unavailable", "demand", "overloaded"]):
                    print(f"[Gemini] Warning: {model_name} API overloaded or quota hit. Switching to next model...")
                    last_error = e
                    continue
                else:
                    # Non-quota error, break out and fail
                    raise e
                    
        if not response:
            raise Exception(f"All Gemini models exhausted their quota limits! Last error: {last_error}")
        
        await client.aio.files.delete(name=uploaded_file.name)
        
        text = response.text
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
            
        data = json.loads(text)
        return GeminiAnalysisSchema(**data)
    except Exception as e:
        raise Exception(f"Gemini API Error: {str(e)}")
