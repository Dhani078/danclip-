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
        print("[Whisper] Loading model 'large-v3' (NVIDIA GPU CUDA int8 mode)...")
        try:
            # int8 CUDA mode fits GTX 1050 Pascal architecture perfectly!
            _whisper_model = WhisperModel("large-v3", device="cuda", compute_type="int8")
            print("[Whisper] SUCCESSFULLY LOADED 'large-v3' ON NVIDIA GPU (CUDA INT8)!")
        except Exception as e:
            try:
                print(f"[Whisper] GPU CUDA large-v3 notice ({e}). Trying GPU 'medium'...")
                _whisper_model = WhisperModel("medium", device="cuda", compute_type="int8")
                print("[Whisper] Successfully loaded 'medium' on NVIDIA GPU (CUDA)!")
            except Exception as e2:
                print(f"[Whisper] GPU CUDA notice ({e2}). Running on CPU 'medium' (int8, 4 threads)...")
                _whisper_model = WhisperModel("medium", device="cpu", compute_type="int8", cpu_threads=4)
                print("[Whisper] Model 'medium' loaded on CPU.")
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


def transcribe_to_ass(audio_path: str, language: str = None, sub_size: int = 100, sub_color: str = "&H00FFFFFF", word_karaoke: bool = False, hook_title: str = "") -> str:
    """
    Transcribe audio file to ASS (Advanced SubStation Alpha) format using Whisper.
    Generates word-by-word karaoke highlighting and optional top hook title banner.
    """
    model = get_whisper_model()
    
    initial_prompt = "Berikut adalah percakapan bahasa Indonesia yang bercampur dengan bahasa Inggris (mixed language). It is a very cool podcast."
    
    segments, info = model.transcribe(
        audio_path,
        language=language,
        initial_prompt=initial_prompt,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    
    actual_font_size = int(sub_size) * 4 if int(sub_size) < 30 else int(sub_size)
    
    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Segoe UI Black,{actual_font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,60,60,320,1
Style: HookHeader,Segoe UI Black,52,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,8,4,8,60,60,240,1

[Events]
Format: Layer, Start, End, Style, Text
"""
    # Kamus Emoji Viral untuk injeksi otomatis pada kata wajib
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
    
    for segment in segments:
        if segment.words:
            words = list(segment.words)
            chunk_size = 2 if word_karaoke else 5  # 2 words for Alex Hormozi, 5 for standard
            
            for i in range(0, len(words), chunk_size):
                chunk = words[i:i + chunk_size]
                if not chunk: continue
                    
                if word_karaoke:
                    # Alex Hormozi style: 1-2 words per line, active word highlighted with sub_color
                    for idx_w, w in enumerate(chunk):
                        clean_word = w.word.strip().replace('.', '').replace(',', '').replace('?', '').replace('!', '').replace('"', '').upper()
                        if not clean_word: continue
                        
                        emoji_prefix = VIRAL_EMOJIS.get(clean_word, "")
                        start_ass = format_ass_time(w.start)
                        end_ass = format_ass_time(w.end)
                        
                        # Emoji remains in neutral white, word receives active highlight color
                        if emoji_prefix:
                            highlighted_text = f"{{\\c&H00FFFFFF&}}{emoji_prefix} {{\\c{sub_color}}}{clean_word}"
                        else:
                            highlighted_text = f"{{\\c{sub_color}}}{clean_word}"
                            
                        ass_events.append(f"Dialogue: 0,{start_ass},{end_ass},Default,{highlighted_text}")
                else:
                    # Standard chunking with emoji support
                    start_ass = format_ass_time(chunk[0].start)
                    end_ass = format_ass_time(chunk[-1].end)
                    
                    line_words = []
                    for w in chunk:
                        clean_word = w.word.strip().replace('.', '').replace(',', '').replace('?', '').replace('!', '').replace('"', '').upper()
                        if not clean_word: continue
                        
                        emoji_prefix = VIRAL_EMOJIS.get(clean_word, "")
                        display_word = f"{emoji_prefix} {clean_word}" if emoji_prefix else clean_word
                        line_words.append(display_word)
                        
                    text = " ".join(line_words)
                    if text:
                        ass_events.append(f"Dialogue: 0,{start_ass},{end_ass},Default,{text}")
                        
        else:
            # Fallback
            start_ass = format_ass_time(segment.start)
            end_ass = format_ass_time(segment.end)
            text = segment.text.strip().replace('.', '').replace(',', '').replace('?', '').replace('!', '').upper()
            if text:
                ass_events.append(f"Dialogue: 0,{start_ass},{end_ass},Default,{text}")
                
    return ass_header + "\n".join(ass_events)


def format_ass_time(seconds: float) -> str:
    """Convert seconds to ASS timestamp format: H:MM:SS.cs"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int((seconds % 1) * 100) # centiseconds
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


async def generate_whisper_srt(input_video: str, start_time: str, end_time: str, temp_dir: str, clip_id: str, sub_size: int = 100, sub_color: str = "&H00FFFFFF", word_karaoke: bool = False, hook_title: str = "") -> str:
    """
    Full pipeline: extract clip audio -> transcribe with Whisper -> return SRT string.
    All timestamps in the returned SRT are relative to clip start (00:00:00).
    """
    audio_path = os.path.join(temp_dir, f"whisper_{clip_id}.wav")
    
    try:
        # Step 1: Extract audio segment
        success = await asyncio.to_thread(extract_clip_audio, input_video, start_time, end_time, audio_path)
        if not success:
            return ""
            
        # Step 2: Transcribe (ASS format is much better for custom styling and karaoke)
        ass_content = await asyncio.to_thread(transcribe_to_ass, audio_path, "id", sub_size, sub_color, word_karaoke, hook_title)
        return ass_content
    except Exception as e:
        print(f"[Whisper STT Error] {e}")
        return ""
    finally:
        # Cleanup temp audio
        if os.path.exists(audio_path):
            os.remove(audio_path)
