"""
Whisper-based Speech-to-Text service.
Uses faster-whisper for frame-accurate subtitle generation.
This replaces AI-generated SRT timestamps which are inherently inaccurate.
"""

import os
import sys
import site
import subprocess
import asyncio
import re
from datetime import datetime

import ctypes
import glob

def escape_ass_text(text: str) -> str:
    """Escapes strings to prevent ASS syntax breakage"""
    if not text: return ""
    return text.replace('{', '｛').replace('}', '｝').replace('\\', '＼')


# Auto-register and pre-load NVIDIA CUDA & cuDNN DLLs into Windows process memory
def _register_cuda_dlls():
    search_paths = []
    try:
        user_site = site.getusersitepackages()
        if isinstance(user_site, str):
            search_paths.append(user_site)
    except Exception:
        pass
    try:
        sys_sites = site.getsitepackages()
        if isinstance(sys_sites, list):
            search_paths.extend(sys_sites)
    except Exception:
        pass

    for sp in search_paths:
        if isinstance(sp, str) and os.path.exists(sp):
            nvidia_base = os.path.join(sp, "nvidia")
            if os.path.exists(nvidia_base):
                for root, dirs, _ in os.walk(nvidia_base):
                    if "bin" in dirs:
                        bin_dir = os.path.join(root, "bin")
                        if bin_dir not in os.environ.get("PATH", ""):
                            os.environ["PATH"] = bin_dir + os.path.pathsep + os.environ.get("PATH", "")
                        try:
                            os.add_dll_directory(bin_dir)
                        except Exception:
                            pass
                # Pre-load all DLL files into process memory
                dll_files = glob.glob(os.path.join(nvidia_base, "*", "bin", "*.dll"))
                for dll_path in dll_files:
                    try:
                        ctypes.cdll.LoadLibrary(dll_path)
                    except Exception:
                        pass

_register_cuda_dlls()

from faster_whisper import WhisperModel

# Global model instance (lazy-loaded once)
_whisper_model = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        model_name = os.environ.get("WHISPER_MODEL", "deepdml/faster-whisper-large-v3-turbo-ct2")
        model_loaded = False
        # First try GPU with float16 or int8
        for cuda_type in ["float16", "int8", "int8_float16"]:
            try:
                print(f"[Whisper] Trying model '{model_name}' on CUDA ({cuda_type})...")
                _whisper_model = WhisperModel(
                    model_name,
                    device="cuda",
                    compute_type=cuda_type,
                    device_index=0
                )
                print(f"[Whisper] SUCCESSFULLY LOADED '{model_name}' ON NVIDIA GPU CUDA ({cuda_type})!")
                model_loaded = True
                break
            except Exception as e:
                print(f"[Whisper Warning] CUDA ({cuda_type}) failed: {e}")
        
        if not model_loaded:
            msg = "GPU tidak tersedia atau tidak mendukung compute type, memakai CPU - proses akan jauh lebih lambat"
            print(f"[Whisper Warning] {msg}")
            import logging
            logging.getLogger(__name__).warning(msg)
            import gc, torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            _whisper_model = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8"
            )
            print(f"[Whisper] SUCCESSFULLY LOADED '{model_name}' ON CPU!")
    return _whisper_model

def unload_whisper_model():
    global _whisper_model
    if _whisper_model is not None:
        print("[Whisper] Unloading model to free VRAM...")
        del _whisper_model
        _whisper_model = None
        import gc
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass


async def extract_clip_audio(input_video: str, start_time: str, end_time: str, output_audio: str) -> bool:
    """Extract audio segment from the original video for a specific clip time range."""
    def parse_time(ts):
        if isinstance(ts, (int, float)): return int(ts)
        ts_str = str(ts).strip()
        parts = ts_str.split(':')
        try:
            if len(parts) == 2: return int(float(parts[0])) * 60 + int(float(parts[1]))
            elif len(parts) == 3: return int(float(parts[0])) * 3600 + int(float(parts[1])) * 60 + int(float(parts[2]))
            return int(float(ts_str))
        except (ValueError, TypeError, IndexError):
            return 0

    t1 = 0
    try:
        t1 = parse_time(start_time)
        t2 = parse_time(end_time)
        duration = str(t2 - t1)
        if (t2 - t1) <= 0:
            duration = "60"
    except Exception:
        duration = "60"

    from services.ffmpeg import FFMPEG_CMD
    cmd = [
        FFMPEG_CMD, "-y",
        "-ss", str(t1),
        "-i", input_video,
        "-t", duration,
        "-vn",
        "-ar", "16000",     # Whisper expects 16kHz
        "-ac", "1",          # Mono
        "-c:a", "pcm_s16le", # WAV format
        output_audio
    ]
    import subprocess
    res = await asyncio.to_thread(
        subprocess.run, cmd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return res.returncode == 0


def apply_multicolor_highlight(clean_word: str, default_color: str = "&H00FFFFFF") -> str:
    """
    Analyzes word context and returns ASS color tag for multi-color word highlighting:
    - Numbers, Money, Percentages -> Yellow (&H0000FFFF)
    - Positive / Action / Impact -> Green (&H0000FF00)
    - Warning / Danger / Stop -> Red (&H000000FF)
    - Special / Curiosity -> Cyan (&H00FFFF00)
    """
    word_upper = clean_word.upper()
    
    # 1. Numbers / Money / Percentage -> Bright Yellow
    if re.search(r'\d', word_upper) or word_upper in ["UANG", "DUIT", "RUPIAH", "JUTA", "MILIAR", "DOLLAR", "PERSEN", "RIBU", "JT", "RB", "PERCENT", "PROSEN"]:
        return f"{{\\c&H0000FFFF&}}{clean_word}"
        
    # 2. Positive / Action / Impact -> Green
    if word_upper in ["SUKSES", "BERHASIL", "UNTUNG", "NAIK", "CEPAT", "MENANG", "BAIK", "TERBAIK", "PRO", "TOP", "KEREN", "MANTAP", "GACOR"]:
        return f"{{\\c&H0000FF00&}}{clean_word}"
        
    # 3. Warning / Danger / Stop -> Red
    if word_upper in ["BAHAYA", "AWAS", "STOP", "JANGAN", "GAGAL", "RUGI", "TURUN", "HATI-HATI", "BURUK", "MATI", "MAMPUS", "SALAH"]:
        return f"{{\\c&H000000FF&}}{clean_word}"
        
    # 4. Special / Curiosity -> Cyan
    if word_upper in ["RAHASIA", "BOCORAN", "TIPS", "TRIK", "CARA", "GRATIS", "BONUS", "BARU", "VIRAL", "TRENDING", "BOMBASTIS", "WOW"]:
        return f"{{\\c&H00FFFF00&}}{clean_word}"

    return f"{{\\c{default_color}}}{clean_word}"

def format_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format: H:MM:SS.cs"""
    try:
        seconds = max(0.0, float(seconds))
    except (ValueError, TypeError):
        seconds = 0.0
    total_cs = int(round(seconds * 100))
    cs = total_cs % 100
    total_sec = total_cs // 100
    s = total_sec % 60
    total_min = total_sec // 60
    m = total_min % 60
    h = total_min // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def transcribe_audio_to_words(audio_path: str, language: str = None, target_language: str = "id") -> list:
    """
    Transcribes the full audio and returns a flat list of dictionaries,
    each representing a word with its timestamps and probabilities.
    """
    import gc
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    lang_param = language if (language and language.lower() != "auto") else None
    
    if lang_param == "id":
        initial_prompt = "Abaikan suara musik dan efek suara. Ini adalah transkrip ucapan percakapan manusia berbahasa Indonesia yang sangat akurat, ejaan sempurna, tata bahasa benar, dan tanpa typo."
    elif lang_param == "en":
        initial_prompt = "Accurate transcript of spoken speech and audio dialogue with perfect spelling and correct grammar."
    else:
        initial_prompt = "Accurate transcription of the spoken audio with perfect spelling, correct grammar, and without any typos."
    whisper_task = "translate" if target_language == "en" else "transcribe"
    
    model = get_whisper_model()
    raw_segments, _ = model.transcribe(
        audio_path,
        language=lang_param,
        task=whisper_task,
        initial_prompt=initial_prompt,
        beam_size=1,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=700, speech_pad_ms=200),
        condition_on_previous_text=False,
        hallucination_silence_threshold=2.0,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
        temperature=[0.0, 0.2, 0.4],
    )
    
    all_words = []
    HALLUCINATION_BLACKLIST = [
        "TERIMA KASIH TELAH MENONTON", "TERIMA KASIH SUDAH MENONTON",
        "SAMPAI JUMPA", "JANGAN LUPA SUBSCRIBE", "TERIMA KASIH",
        "SUBTITLE BY AMARA", "SUBSCRIBE", "SUBSCRIBE YA"
    ]
    
    for segment in raw_segments:
        seg_text_clean = segment.text.strip().replace('.', '').replace(',', '').replace('?', '').replace('!', '').replace('"', '').upper()
        is_suspicious = any(seg_text_clean == bad for bad in HALLUCINATION_BLACKLIST) or "TERIMA KASIH TELAH MENONTON" in seg_text_clean
        
        no_speech = getattr(segment, "no_speech_prob", 0)
        if is_suspicious and no_speech > 0.2:
            print(f"[Whisper STT] 🛑 Hallucination suppressed: '{segment.text}' (no_speech_prob={no_speech:.3f})")
            continue
            
        if segment.words:
            for w in segment.words:
                all_words.append({"start": w.start, "end": w.end, "word": w.word})
        else:
            # Fallback if words aren't available but segment is valid
            all_words.append({"start": segment.start, "end": segment.end, "word": segment.text})
            
    return all_words

def generate_ass_from_words(
    words: list, 
    clip_start: float, 
    clip_end: float,
    sub_size: int = 100, 
    sub_color: str = "&H00FFFFFF", 
    word_karaoke: bool = False, 
    hook_title: str = "", 
    subtitle_preset: str = "hormozi", 
    subtitle_position: str = "bottom",
    sub_opacity: int = 100
) -> str:
    """Generates an ASS subtitle string for a specific clip duration using pre-transcribed words."""
    preset = (subtitle_preset or "hormozi").lower()
    
    margin_v = 300
    alignment_val = 2
    pos = str(subtitle_position or "bottom").lower()
    if pos == "top":
        margin_v = 1500
        alignment_val = 8
    elif pos in ["middle", "center"]:
        margin_v = 900
        alignment_val = 5
    elif pos.isdigit():
        margin_v = int(pos)
        
    font_name = "Segoe UI Black"
    actual_font_size = sub_size
    alpha_val = int((100 - max(0, min(100, sub_opacity))) * 2.55)
    alpha_hex = f"{alpha_val:02X}"
    raw_color = str(sub_color or "").replace("&H", "").replace("#", "").zfill(6)[-6:]
    ass_sub_color = f"&H{raw_color}&"
    primary_color = f"&H{alpha_hex}{raw_color}"
    back_color = "&H80000000"
    border_style = 1
    outline_val = 6
    shadow_val = 3
    extra_tags = ""
    
    if preset == "mrbeast":
        font_name = "Impact"
        actual_font_size = int(actual_font_size * 1.15)
        primary_color = f"&H{alpha_hex}00FFFF"
        outline_val = 8
        shadow_val = 4
    elif preset == "ali_abdaal":
        font_name = "Georgia"
        actual_font_size = int(actual_font_size * 0.85)
        primary_color = f"&H{alpha_hex}F0F0F0"
        back_color = "&HAA151515"
        border_style = 3
        outline_val = 2
        shadow_val = 0
    elif preset == "tiktok_neon":
        font_name = "Segoe UI Black"
        primary_color = f"&H{alpha_hex}FFFFFF"
        back_color = "&H00FFFF00"
        outline_val = 5
        shadow_val = 5
        extra_tags = "{\\blur5}"
       
    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{actual_font_size},{primary_color},&H000000FF,&H00000000,{back_color},-1,0,0,0,100,100,0,0,{border_style},{outline_val},{shadow_val},{alignment_val},60,60,{margin_v},1
Style: HookHeader,Segoe UI Black,62,&H0000F7FF,&H000000FF,&H00000000,&HCC000000,-1,0,0,0,100,100,0,0,1,10,6,8,60,60,240,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    VIRAL_EMOJIS = {
        "UANG": "💸", "DUIT": "💰", "RUPIAH": "💴", "JUTA": "💵", "MILIAR": "💎", "DOLLAR": "💲",
        "SUKSES": "🔥", "BERHASIL": "✅", "CEPAT": "⚡", "MENANG": "🏆", "TOP": "🥇", "PRO": "😎",
        "BAHAYA": "⚠️", "NANGIS": "😭", "SEDIH": "😢", "TAWA": "😂", 
        "LUCU": "🤣", "MAMPUS": "💀", "MATI": "☠️", "KERJA": "💼",
        "KAYA": "🤑", "MISKIN": "📉", "UNTUNG": "📈", "RUGI": "📉", 
        "NAIK": "🚀", "TURUN": "📉", "MAKAN": "🍔", "MINUM": "☕", 
        "TIDUR": "😴", "BACA": "📖", "OTAK": "🧠", "TUHAN": "🙏", 
        "DOA": "🤲", "AMIN": "🙏", "BINTANG": "⭐", "PETIR": "⚡",
        "WOW": "😲", "WAH": "😮", "KAGET": "🙀"
    }

    ass_events = []
    if hook_title:
        clean_hook = escape_ass_text(hook_title.strip().upper())
        # Pop-in animation: scale from 80% to 110% in 0.8s, then settle to 100% by 1.5s
        pop_anim = r"{\an8\fscx80\fscy80\t(0,800,\fscx110\fscy110)\t(800,1500,\fscx100\fscy100)}"
        ass_events.append(f"Dialogue: 0,0:00:00.00,0:00:04.50,HookHeader,{pop_anim}{clean_hook}")
    
    use_multicolor = (preset in ["mrbeast", "multicolor"])
    chunk_size = 2 if (word_karaoke or preset in ["hormozi", "mrbeast", "tiktok_neon"]) else 5
    
    # Filter words strictly in the clip's time range
    clip_words = []
    for w in words:
        if w["end"] > clip_start and w["start"] < clip_end:
            clip_words.append(w)
            
    for i in range(0, len(clip_words), chunk_size):
        chunk = clip_words[i:i + chunk_size]
        if not chunk: continue
            
        if word_karaoke or preset in ["hormozi", "mrbeast", "tiktok_neon"]:
            # Word-by-word active highlight / multi-color style
            for idx_w, w in enumerate(chunk):
                clean_word = w["word"].strip().replace('.', '').replace(',', '').replace('?', '').replace('!', '').replace('"', '').upper()
                clean_word = escape_ass_text(clean_word)
                if not clean_word: continue
                
                emoji_prefix = VIRAL_EMOJIS.get(clean_word, "")
                # Adjust timestamps relative to clip start
                adjusted_start = max(0, w["start"] - clip_start)
                adjusted_end = max(0, w["end"] - clip_start)
                
                # FIX FLICKERING: Bridge gap to the next word if it's close
                if idx_w + 1 < len(chunk):
                    next_word = chunk[idx_w + 1]
                elif i + chunk_size < len(clip_words):
                    next_word = clip_words[i + chunk_size]
                else:
                    next_word = None
                
                if next_word:
                    next_start = max(0, next_word["start"] - clip_start)
                    # If gap is less than 0.8 seconds, keep word on screen
                    if next_start > adjusted_end and (next_start - adjusted_end) < 0.8:
                        adjusted_end = next_start
                
                start_ass = format_ass_time(adjusted_start)
                # Guarantee minimum 0.25s duration per word so FFmpeg never drops ultra-fast words
                end_ass = format_ass_time(max(adjusted_end, adjusted_start + 0.25))
                
                if use_multicolor:
                    styled_text = apply_multicolor_highlight(clean_word, ass_sub_color)
                else:
                    styled_text = f"{{\\c{ass_sub_color}}}{clean_word}"
                    
                if emoji_prefix:
                    highlighted_text = f"{extra_tags}{{\\c&H00FFFFFF&}}{emoji_prefix} {styled_text}"
                else:
                    highlighted_text = f"{extra_tags}{styled_text}"
                    
                ass_events.append(f"Dialogue: 0,{start_ass},{end_ass},Default,{highlighted_text}")
        else:
            # Standard chunking
            adjusted_start = max(0, chunk[0]["start"] - clip_start)
            adjusted_end = max(0, chunk[-1]["end"] - clip_start)
            
            # FIX FLICKERING: Bridge gap to the next chunk
            if i + chunk_size < len(clip_words):
                next_chunk_first_word = clip_words[i + chunk_size]
                next_start = max(0, next_chunk_first_word["start"] - clip_start)
                if next_start > adjusted_end and (next_start - adjusted_end) < 0.8:
                    adjusted_end = next_start
            
            start_ass = format_ass_time(adjusted_start)
            end_ass = format_ass_time(max(adjusted_end, adjusted_start + 0.30))
            
            line_words = []
            for w in chunk:
                clean_word = w["word"].strip().replace('.', '').replace(',', '').replace('?', '').replace('!', '').replace('"', '').upper()
                clean_word = escape_ass_text(clean_word)
                if not clean_word: continue
                
                emoji_prefix = VIRAL_EMOJIS.get(clean_word, "")
                if use_multicolor:
                    styled_word = apply_multicolor_highlight(clean_word, ass_sub_color)
                else:
                    styled_word = clean_word
                    
                if emoji_prefix:
                    line_words.append(f"{{\\c&H00FFFFFF&}}{emoji_prefix} {styled_word}")
                else:
                    line_words.append(styled_word)
                    
            if not line_words: continue
            
            combined_text = " ".join(line_words)
            if not use_multicolor:
                combined_text = f"{{\\c{ass_sub_color}}}{combined_text}"
            
            ass_events.append(f"Dialogue: 0,{start_ass},{end_ass},Default,{extra_tags}{combined_text}")
            
    return ass_header + "\n".join(ass_events) + "\n"

async def generate_whisper_srt(input_video: str, start_time: str, end_time: str, temp_dir: str, clip_id: str, sub_size: int = 100, sub_color: str = "&H00FFFFFF", word_karaoke: bool = False, hook_title: str = "", subtitle_preset: str = "hormozi", subtitle_position: str = "bottom", target_language: str = "id", sub_opacity: int = 100) -> str:
    """
    Backwards compatibility layer: Extracts a single clip's audio, transcribes it, and generates ASS.
    """
    audio_path = os.path.join(temp_dir, f"clip_{clip_id}.wav")
    
    success = await extract_clip_audio(input_video, start_time, end_time, audio_path)
    if not success or not os.path.exists(audio_path):
        return ""
        
    def parse_time(ts):
        if isinstance(ts, (int, float)): return int(ts)
        ts_str = str(ts).strip()
        parts = ts_str.split(':')
        try:
            if len(parts) == 2: return int(float(parts[0])) * 60 + int(float(parts[1]))
            elif len(parts) == 3: return int(float(parts[0])) * 3600 + int(float(parts[1])) * 60 + int(float(parts[2]))
            return int(float(ts_str))
        except (ValueError, TypeError, IndexError):
            return 0
        
    start_sec = parse_time(start_time)
    end_sec = parse_time(end_time)
        
    try:
        import asyncio
        words = await asyncio.to_thread(transcribe_audio_to_words, audio_path, "auto", target_language)
        # For a single clip, the words already start at 0 relative to the audio file
        # So we pass 0 as clip_start to avoid subtracting again
        ass_content = generate_ass_from_words(
            words, 0.0, float(end_sec - start_sec), 
            sub_size=sub_size, sub_color=sub_color, word_karaoke=word_karaoke,
            hook_title=hook_title, subtitle_preset=subtitle_preset,
            subtitle_position=subtitle_position, sub_opacity=sub_opacity
        )
        return ass_content
    except Exception as e:
        print(f"[Whisper ERROR in backwards-compat]: {e}")
        return ""
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

