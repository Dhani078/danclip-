import asyncio
import os
import re
from datetime import datetime

def detect_faces_and_recommend_layout(video_path: str, start_time_sec: float, duration_sec: float = 30.0) -> dict:
    """
    Uses OpenCV YuNet face detection to analyze multiple video frames across clip duration.
    Smart Podcast Detection:
    - If >= 2 distinct speakers are detected in majority of frames -> Recommend Top/Bottom Split-Screen with left & right speaker centering.
    - If 1 face is detected (e.g., camera cuts 2-5 sec to single speaker) -> Recommend Single-Face Center Crop.
    - If 0 faces found -> Recommend Blur-Pad background.
    """
    import cv2
    import numpy as np
    from services.face_tracker import ensure_yunet_model, YUNET_MODEL_PATH
    
    ensure_yunet_model()
    model_path = YUNET_MODEL_PATH
    if not os.path.exists(model_path):
        model_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "face_detection_yunet_2023mar.onnx")
        
    if not os.path.exists(model_path):
        return {"num_faces": 1, "is_split_screen": False, "face_center_x_ratio": 0.5, "use_blur_pad": False}
        
    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        
        # Sample 8 keyframes across clip (from 5% at start up to 95% at end of clip duration)
        sample_times = [
            start_time_sec + max(0.2, duration_sec * 0.05),
            start_time_sec + max(1.0, duration_sec * 0.18),
            start_time_sec + max(2.0, duration_sec * 0.31),
            start_time_sec + max(3.0, duration_sec * 0.44),
            start_time_sec + max(4.0, duration_sec * 0.57),
            start_time_sec + max(5.0, duration_sec * 0.70),
            start_time_sec + max(6.0, duration_sec * 0.83),
            start_time_sec + max(7.0, duration_sec * 0.95)
        ]
        
        ratios_x = []
        ratios_y = []
        face_counts = []
        left_faces_x = []
        right_faces_x = []
        
        for st in sample_times:
            target_frame = max(0, int(st * fps))
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
                
            h, w, _ = frame.shape
            # Lower score threshold to 0.35 to catch side-profile faces or angled poses
            detector = cv2.FaceDetectorYN.create(model_path, "", (w, h), score_threshold=0.35)
            _, faces = detector.detect(frame)
            
            if faces is not None and len(faces) > 0:
                faces_sorted = sorted(faces, key=lambda f: f[2], reverse=True)
                main_face_width = faces_sorted[0][2]
                # Filter significant faces (at least 40% as big as main face to ignore background passersby)
                significant_faces = [f for f in faces if f[2] >= main_face_width * 0.4]
                face_counts.append(len(significant_faces))
                
                # Sort faces left-to-right by X position for podcast dual-speaker tracking
                faces_by_x = sorted(significant_faces, key=lambda f: f[0])
                if len(faces_by_x) >= 2:
                    f_left = faces_by_x[0]
                    f_right = faces_by_x[-1]
                    left_x_center = (f_left[0] + f_left[2] / 2.0) / float(w)
                    right_x_center = (f_right[0] + f_right[2] / 2.0) / float(w)
                    left_faces_x.append(left_x_center)
                    right_faces_x.append(right_x_center)

                main_face = faces_sorted[0]
                face_center_x = main_face[0] + main_face[2] / 2.0
                face_eye_y = main_face[1] + main_face[3] * 0.35
                
                ratios_x.append(face_center_x / float(w))
                ratios_y.append(face_eye_y / float(h))
            else:
                face_counts.append(0)
                
        cap.release()
        
        # If 0 faces found in majority of sampled frames (>= 6 out of 8 frames with 0 faces), it's a B-roll/Slide scene -> Blur-Pad!
        zero_face_frames = face_counts.count(0)
        if not ratios_x or zero_face_frames >= 6:
            return {"num_faces": 0, "is_split_screen": False, "face_center_x_ratio": None, "face_center_y_ratio": None, "use_blur_pad": True}
            
        median_x = float(np.median(ratios_x))
        median_y = float(np.median(ratios_y))
        
        bounded_x = max(0.1, min(0.9, median_x))
        bounded_y = max(0.1, min(0.9, median_y))
        max_faces = int(max(face_counts))

        # Split screen threshold: If at least 3 sampled frames have 2 distinct side-by-side speakers
        is_split = len(left_faces_x) >= 3 and max_faces >= 2
        
        result = {
            "num_faces": max_faces, 
            "is_split_screen": is_split,
            "face_center_x_ratio": bounded_x, 
            "face_center_y_ratio": bounded_y, 
            "use_blur_pad": False
        }
        
        if is_split:
            result["face_left_x_ratio"] = float(np.median(left_faces_x))
            result["face_right_x_ratio"] = float(np.median(right_faces_x))
            
        return result
    except Exception as e:
        print(f"[YuNet Face Tracker Warning] {e}")
        return {"num_faces": 1, "is_split_screen": False, "face_center_x_ratio": 0.5, "use_blur_pad": False}

async def render_viral_clip(input_path: str, output_path: str, start_time: str, end_time: str, subtitle_path: str = None, settings: dict = None, burn_subtitles: bool = False):
    """
    Renders the video using dynamic settings (aspect ratio, crop style).
    Integrates YuNet face detection & adaptive scene detection (B-roll, podcast dual-speaker split screen, single speaker tracking).
    """
    if settings is None or not isinstance(settings, dict):
        settings = {}
        
    aspect_ratio = settings.get("aspect_ratio", "9:16")
    crop_style = settings.get("crop_style", "center_crop")
    sub_color = settings.get("subtitle_color", "&H00FFFF")
    sub_size = settings.get("subtitle_size", 11)
    subtitle_opacity = settings.get("subtitle_opacity", 100)
    
    auto_reframe = settings.get("auto_reframe", False)
    word_karaoke = settings.get("word_karaoke", False)
    bgm_ducking = settings.get("bgm_ducking", False)
    has_broll = settings.get("has_broll", False)
    
    if aspect_ratio == "9:16":
        tw, th = 1080, 1920
    elif aspect_ratio == "4:5":
        tw, th = 1080, 1350
    elif aspect_ratio == "1:1":
        tw, th = 1080, 1080
    else:
        tw, th = 1080, 1920
        
    bgm_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "bgm.mp3")
    has_bgm = bgm_ducking and os.path.exists(bgm_path)

    layout_mode = settings.get("layout_mode", "auto") # "auto", "single", "split"
    
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
    except:
        duration = "60"

    # Step: YuNet Face & Scene Detection (Multi-Keyframe Sampling)
    face_info = await asyncio.to_thread(detect_faces_and_recommend_layout, input_path, float(t1), float(duration))
    print(f"[FFmpeg Engine] Multi-Keyframe Scene & Face Analysis: {face_info}")
    
    # Determine split screen mode
    if layout_mode == "split":
        should_split = True
    elif layout_mode == "single":
        should_split = False
    else: # "auto" mode
        should_split = face_info.get("is_split_screen", False)
        
    # Auto-adapt to blur_pad ONLY if zero faces found by YuNet across frames, or user explicitly chose blur_pad
    if crop_style == "blur_pad" or (crop_style == "center_crop" and face_info["use_blur_pad"]):
        effective_crop_style = "blur_pad"
    else:
        effective_crop_style = "center_crop"
    
    if effective_crop_style == "center_crop":
        if auto_reframe and should_split and face_info["num_faces"] >= 2:
            # Opus Clip Smart Dual-Speaker Podcast Split Screen
            left_x = face_info.get("face_left_x_ratio", 0.28)
            right_x = face_info.get("face_right_x_ratio", 0.72)
            
            # Ultra Robust Scale Filter for half-height split screen (width >= tw, height >= th//2)
            scale_split = rf"scale=w='max({tw}\, iw*{th//2}/ih)':h='max({th//2}\, ih*{tw}/iw)'"
            
            # Crop expressions for Left (Top Half) and Right (Bottom Half) speakers
            top_x_expr = rf"max(0\, min(in_w-{tw}\, in_w*{left_x:.3f} - {tw}/2))"
            bottom_x_expr = rf"max(0\, min(in_w-{tw}\, in_w*{right_x:.3f} - {tw}/2))"
            
            filter_complex = (
                f"[0:v]split=2[top_raw][bottom_raw];"
                rf"[top_raw]{scale_split},crop={tw}:{th//2}:{top_x_expr}:(in_h-{th//2})/2[top];"
                rf"[bottom_raw]{scale_split},crop={tw}:{th//2}:{bottom_x_expr}:(in_h-{th//2})/2[bottom];"
                f"[top][bottom]vstack[v]"
            )
        elif auto_reframe:
            # Dynamic Single Face Tracking crop (X and Y Rule of Thirds)
            ratio_x = float(face_info["face_center_x_ratio"]) if face_info.get("face_center_x_ratio") is not None else 0.5
            ratio_y = float(face_info["face_center_y_ratio"]) if face_info.get("face_center_y_ratio") is not None else 0.35
            
            x_crop_expr = rf"max(0\, min(in_w-{tw}\, in_w*{ratio_x:.3f} - {tw}/2))"
            y_crop_expr = rf"max(0\, min(in_h-{th}\, in_h*{ratio_y:.3f} - {th}*0.28))"
            
            filter_complex = f"[0:v]scale=-1:{th}:force_original_aspect_ratio=increase,crop={tw}:{th}:{x_crop_expr}:{y_crop_expr}[v]"
        else:
            filter_complex = f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th}[v]"
    else: # blur_pad
        filter_complex = (
            f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},boxblur=40:10,drawbox=x=0:y=0:w=iw:h=ih:color=black@0.6:t=fill[bg];"
            f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2[v]"
        )
    
    if subtitle_path and burn_subtitles and os.path.exists(subtitle_path):
        ass_path_escaped = subtitle_path.replace('\\', '/')
        sub_filter = f"[v]ass='{ass_path_escaped}'[v2]"
        filter_complex += f";{sub_filter}"
        map_v = "[v2]"
    else:
        map_v = "[v]"
        
    map_a = "[a_out]"
    if has_bgm:
        # BGM ducking using sidechaincompress + Broadcast EBU R128 Loudness Normalization
        audio_filter = (
            ";[1:a]volume=0.3[bgm_vol];"
            "[0:a]asplit[a_main][a_side];"
            "[bgm_vol][a_side]sidechaincompress=threshold=0.08:ratio=10:attack=100:release=1000[bgm_ducked];"
            "[a_main][bgm_ducked]amix=inputs=2:duration=first:dropout_transition=2,loudnorm=I=-16:TP=-1.5:LRA=11[a_out]"
        )
        filter_complex += audio_filter
    else:
        # Professional Broadcast EBU R128 Loudness Normalization (-16 LUFS for TikTok/Reels)
        audio_filter = ";[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[a_out]"
        filter_complex += audio_filter
    
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(t1),
        "-i", input_path
    ]
    
    if has_bgm:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_path])
        
    cmd.extend([
        "-t", duration,
        "-filter_complex", filter_complex,
        "-map", map_v,
        "-map", map_a,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-threads", "4",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-async", "1",
        output_path
    ])
    
    import subprocess
    def run_ffmpeg(command):
        return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
    process = await asyncio.to_thread(run_ffmpeg, cmd)
    if process.returncode != 0:
        raise Exception(f"FFmpeg failed with error: {process.stderr.decode()}")
        
    print("[FFmpeg] Clip rendered successfully!")
    return output_path
