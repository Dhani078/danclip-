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
        model_name = os.environ.get("WHISPER_MODEL", "large-v3")
        try:
            print(f"[Whisper] Loading model '{model_name}' on NVIDIA GPU CUDA (int8 mode)...")
            _whisper_model = WhisperModel(
                model_name,
                device="cuda",
                compute_type="int8",
                device_index=0
            )
            print(f"[Whisper] SUCCESSFULLY LOADED '{model_name}' ON NVIDIA GPU CUDA!")
        except Exception as e:
            print(f"[Whisper Warning] GPU Loading Failed: {e}. Falling back to CPU mode...")
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


def extract_clip_audio(input_video: str, start_time: str, end_time: str, output_audio: str) -> bool:
    """Extract audio segment from the original video for a specific clip time range."""
    def parse_time(ts_str):
        parts = ts_str.split(':')
        if len(parts) == 2: # MM:SS
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3: # HH:MM:SS
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
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

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(t1),
        "-i", input_video,
        "-t", duration,
        "-vn",
        "-ar", "16000",     # Whisper expects 16kHz
        "-ac", "1",          # Mono
        "-c:a", "pcm_s16le", # WAV format
        output_audio
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.returncode == 0


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
        
    # 2. High Impact / Positive / Success -> Neon Green
    if word_upper in ["KEREN", "SUKSES", "KAYA", "JATUH", "BANGKIT", "MENANG", "JUARA", "RAHASIA", "UNTUNG", "NAIK", "BOOM", "PECAH", "GILA", "TERBAIK", "POWER", "STRATEGI", "TIPS", "IDE"]:
        return f"{{\\c&H0000FF00&}}{clean_word}"
        
    # 3. Danger / Warning / Negative / Stop -> Crimson Red
    if word_upper in ["JANGAN", "BAHAYA", "SALAH", "GAGAL", "RUGI", "STOP", "BOHONG", "HATI-HATI", "WARNING", "TAKUT", "MAMPUS", "MATI", "STRES"]:
        return f"{{\\c&H000000FF&}}{clean_word}"
        
    # 4. Special / Curiosity -> Bright Cyan
    if word_upper in ["APA", "KENAPA", "BAGAIMANA", "KOK", "WOW", "BISA", "CARA"]:
        return f"{{\\c&H00FFFF00&}}{clean_word}"
        
    return f"{{\\c{default_color}}}{clean_word}"


def transcribe_to_ass(audio_path: str, language: str = None, sub_size: int = 100, sub_color: str = "&H00FFFFFF", word_karaoke: bool = False, hook_title: str = "", subtitle_preset: str = "hormozi", subtitle_position: str = "bottom", target_language: str = "id") -> str:
    """
    Transcribe audio file to ASS format using Whisper.
    Supports Preset Subtitle Styles, Dynamic Vertical Positioning, and Multi-Language Translation.
    - 'target_language': 'id' (Original/Indonesian), 'en' (Auto-Translate to English), etc.
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
        # Universal prompt for all other languages globally
        initial_prompt = "Accurate transcription of the spoken audio with perfect spelling, correct grammar, and without any typos."
    whisper_task = "translate" if target_language == "en" else "transcribe"
    
    try:
        model = get_whisper_model()
        
        # Beam size 5 provides better accuracy (less typos). Advanced VAD + Hallucination filters.
        raw_segments, info = model.transcribe(
            audio_path,
            language=lang_param,
            task=whisper_task,
            initial_prompt=initial_prompt,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=1000, speech_pad_ms=600),
            condition_on_previous_text=False, # Critical for large-v3 to prevent infinite loops
            hallucination_silence_threshold=2.0, # Automatically drop hallucinated loops in silence
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
        )
        segments = list(raw_segments)
    except Exception as gpu_err:
        print(f"[Whisper GPU Warning] {gpu_err}. Hard resetting CUDA context & retrying...")
        # 1. Completely destroy the broken CUDA model
        global _whisper_model
        if _whisper_model is not None:
            del _whisper_model
            _whisper_model = None
            
        # 2. Aggressive VRAM purge
        import gc
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
            
        # 3. Fallback to CPU to guarantee completion without hanging
        print("[Whisper] GPU OOM encountered. Falling back to CPU mode (this will be slower but guaranteed to finish)...")
        from faster_whisper import WhisperModel
        model_name = os.environ.get("WHISPER_MODEL", "large-v3")
        cpu_model = WhisperModel(model_name, device="cpu", compute_type="int8")
        raw_segments, info = cpu_model.transcribe(
            audio_path,
            language=lang_param,
            task=whisper_task,
            initial_prompt=initial_prompt,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=1000, speech_pad_ms=600),
            condition_on_previous_text=False, # Critical for large-v3 to prevent infinite loops
            hallucination_silence_threshold=2.0, # Automatically drop hallucinated loops in silence
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
        )
        segments = list(raw_segments)
    
    actual_font_size = int(sub_size) * 4 if int(sub_size) < 30 else int(sub_size)
    preset = (subtitle_preset or "hormozi").lower()
    
    # Position mapping for ASS Vertical Margin & Alignment
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
        alignment_val = 2
        
    # Configure ASS Styles based on preset
    font_name = "Segoe UI Black"
    primary_color = sub_color if sub_color else "&H00FFFFFF"
    back_color = "&H80000000"
    border_style = 1
    outline_val = 6
    shadow_val = 3
    extra_tags = ""
    
    if preset == "mrbeast":
        font_name = "Impact"
        actual_font_size = int(actual_font_size * 1.15)
        primary_color = "&H0000FFFF" # Yellow
        outline_val = 8
        shadow_val = 4
    elif preset == "ali_abdaal":
        font_name = "Georgia"
        actual_font_size = int(actual_font_size * 0.85)
        primary_color = "&H00F0F0F0" # Soft White
        back_color = "&HAA151515"   # Opaque Dark Box
        border_style = 3            # Opaque Box Style
        outline_val = 2
        shadow_val = 0
    elif preset == "tiktok_neon":
        font_name = "Segoe UI Black"
        primary_color = "&H00FFFFFF"
        back_color = "&H00FFFF00"   # Cyan Neon Glow
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
Style: HookHeader,Segoe UI Black,52,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,8,4,8,60,60,240,1

[Events]
Format: Layer, Start, End, Style, Text
"""

    VIRAL_EMOJIS = {
        "UANG": "💰", "CASH": "💵", "DUIT": "💸", "RUPIAH": "💴",
        "MARAH": "😡", "KESEL": "😤", "GILA": "🤯", "STRES": "😫",
        "API": "🔥", "KEREN": "🔥", "PECAH": "💥", "BOOM": "💥",
        "CINTA": "❤️", "SAYANG": "💕", "HATI": "💖",
        "BOHONG": "🤥", "PINTAR": "🧠", "CERDAS": "💡", "IDE": "💡",
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
        clean_hook = hook_title.strip().upper()
        ass_events.append(f"Dialogue: 0,0:00:00.00,0:00:04.50,HookHeader,{{\\an8}}{clean_hook}")
    
    use_multicolor = (preset in ["mrbeast", "multicolor"])
    chunk_size = 2 if (word_karaoke or preset in ["hormozi", "mrbeast", "tiktok_neon"]) else 5
    
    for segment in segments:
        if segment.words:
            words = list(segment.words)
            
            for i in range(0, len(words), chunk_size):
                chunk = words[i:i + chunk_size]
                if not chunk: continue
                    
                if word_karaoke or preset in ["hormozi", "mrbeast", "tiktok_neon"]:
                    # Word-by-word active highlight / multi-color style
                    for idx_w, w in enumerate(chunk):
                        clean_word = w.word.strip().replace('.', '').replace(',', '').replace('?', '').replace('!', '').replace('"', '').upper()
                        if not clean_word: continue
                        
                        emoji_prefix = VIRAL_EMOJIS.get(clean_word, "")
                        start_ass = format_ass_time(w.start)
                        # Guarantee minimum 0.25s duration per word so FFmpeg never drops ultra-fast words
                        end_ass = format_ass_time(max(w.end, w.start + 0.25))
                        
                        if use_multicolor:
                            styled_text = apply_multicolor_highlight(clean_word, primary_color.replace("&H00", ""))
                        else:
                            styled_text = f"{{\\c{sub_color}}}{clean_word}"
                            
                        if emoji_prefix:
                            highlighted_text = f"{extra_tags}{{\\c&H00FFFFFF&}}{emoji_prefix} {styled_text}"
                        else:
                            highlighted_text = f"{extra_tags}{styled_text}"
                            
                        ass_events.append(f"Dialogue: 0,{start_ass},{end_ass},Default,{highlighted_text}")
                else:
                    # Standard chunking
                    start_ass = format_ass_time(chunk[0].start)
                    end_ass = format_ass_time(max(chunk[-1].end, chunk[0].start + 0.30))
                    
                    line_words = []
                    for w in chunk:
                        clean_word = w.word.strip().replace('.', '').replace(',', '').replace('?', '').replace('!', '').replace('"', '').upper()
                        if not clean_word: continue
                        
                        emoji_prefix = VIRAL_EMOJIS.get(clean_word, "")
                        if use_multicolor:
                            styled_word = apply_multicolor_highlight(clean_word, primary_color.replace("&H00", ""))
                        else:
                            styled_word = clean_word
                            
                        display_word = f"{emoji_prefix} {styled_word}" if emoji_prefix else styled_word
                        line_words.append(display_word)
                        
                    text = " ".join(line_words)
                    if text:
                        ass_events.append(f"Dialogue: 0,{start_ass},{end_ass},Default,{extra_tags}{text}")
        else:
            start_ass = format_ass_time(segment.start)
            end_ass = format_ass_time(max(segment.end, segment.start + 0.30))
            text = segment.text.strip().replace('.', '').replace(',', '').replace('?', '').replace('!', '').upper()
            if text:
                ass_events.append(f"Dialogue: 0,{start_ass},{end_ass},Default,{extra_tags}{text}")
                
    return ass_header + "\n".join(ass_events)


def format_ass_time(seconds: float) -> str:
    """Convert seconds to ASS timestamp format: H:MM:SS.cs"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int((seconds % 1) * 100) # centiseconds
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


async def generate_whisper_srt(input_video: str, start_time: str, end_time: str, temp_dir: str, clip_id: str, sub_size: int = 100, sub_color: str = "&H00FFFFFF", word_karaoke: bool = False, hook_title: str = "", subtitle_preset: str = "hormozi", subtitle_position: str = "bottom", target_language: str = "id") -> str:
    """
    Full pipeline: extract clip audio -> transcribe with Whisper -> return ASS string.
    All timestamps in the returned ASS are relative to clip start (00:00:00).
    """
    audio_path = os.path.join(temp_dir, f"whisper_{clip_id}.wav")
    
    try:
        # Step 1: Extract audio segment
        success = await asyncio.to_thread(extract_clip_audio, input_video, start_time, end_time, audio_path)
        if not success:
            return ""
            
        # Step 2: Transcribe (ASS format with preset styles, vertical positioning, translation & multi-color highlighting)
        ass_content = await asyncio.to_thread(transcribe_to_ass, audio_path, None, sub_size, sub_color, word_karaoke, hook_title, subtitle_preset, subtitle_position, target_language)
        return ass_content
    except Exception as e:
        print(f"[Whisper STT Error] {e}")
        return ""
    finally:
        # Cleanup temp audio
        if os.path.exists(audio_path):
            os.remove(audio_path)
