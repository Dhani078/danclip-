import os
import cv2
import numpy as np
import urllib.request

YUNET_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models_data", "face_detection_yunet.onnx")

def ensure_yunet_model():
    """Ensure the 300KB OpenCV YuNet Face Detection model file exists."""
    os.makedirs(os.path.dirname(YUNET_MODEL_PATH), exist_ok=True)
    if not os.path.exists(YUNET_MODEL_PATH):
        print("[FaceTracker] Downloading YuNet Face Detector model (300 KB)...")
        url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
        urllib.request.urlretrieve(url, YUNET_MODEL_PATH)
        print("[FaceTracker] Model downloaded successfully.")

def detect_faces_in_video(video_path: str, max_samples: int = 15) -> list:
    """
    Samples frames from a video file and detects faces using OpenCV YuNet.
    Returns a list of detected face center X coordinates (normalized 0.0 to 1.0).
    """
    ensure_yunet_model()
    if not os.path.exists(video_path):
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    if total_frames <= 0 or frame_width <= 0 or frame_height <= 0:
        cap.release()
        return []

    detector = cv2.FaceDetectorYN.create(YUNET_MODEL_PATH, "", (frame_width, frame_height))
    
    step = max(1, total_frames // max_samples)
    face_centers = []

    for frame_idx in range(0, total_frames, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        detector.setInputSize((frame_width, frame_height))
        _, faces = detector.detect(frame)
        
        if faces is not None and len(faces) > 0:
            for face in faces:
                # face format: [x, y, w, h, x_re, y_re, x_le, y_le, x_n, y_n, x_rm, y_rm, score]
                box_x, box_y, box_w, box_h = face[:4]
                score = face[-1]
                if score >= 0.6:  # confidence threshold
                    center_x = (box_x + box_w / 2.0) / frame_width
                    face_centers.append(center_x)

    cap.release()
    return face_centers

def calculate_smart_crop_offset(video_path: str, target_aspect: str = "9:16") -> float:
    """
    Calculates the optimal crop X offset ratio (0.0 to 1.0) to center around detected faces.
    If no face detected or 50% split, defaults to 0.5 (center).
    """
    try:
        centers = detect_faces_in_video(video_path, max_samples=12)
        if not centers:
            print("[FaceTracker] No prominent face detected. Falling back to center crop (0.5).")
            return 0.5

        # Calculate median face position to prevent outlier jumps
        median_x = float(np.median(centers))
        print(f"[FaceTracker] Detected face center median: {median_x:.3f}")
        return max(0.15, min(0.85, median_x))
    except Exception as e:
        print(f"[FaceTracker Warning] Face tracking failed: {e}. Defaulting to center.")
        return 0.5

async def apply_ema_tracking_to_video(input_path: str, output_path: str, start_time_sec: float, duration_sec: float, tw: int = 1080, th: int = 1920) -> bool:
    """
    Applies true auto-reframing with EMA-based tracking and a 3% deadzone.
    Outputs a pre-cropped, track-smoothed video (without audio).
    Uses fast FFmpeg piping to encode.
    """
    import asyncio
    import subprocess
    from services.ffmpeg import get_best_encoder # Import encoder selection
    
    ensure_yunet_model()
    if not os.path.exists(input_path):
        return False
        
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        return False
        
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    if orig_w == 0 or orig_h == 0:
        cap.release()
        return False
        
    # Seek to start frame
    start_frame = max(0, int(start_time_sec * fps))
    end_frame = start_frame + int(duration_sec * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    
    # Scale to fill both tw and th minimum dimensions
    scale_factor = max(tw / float(orig_w), th / float(orig_h))
    new_w = max(tw, int(orig_w * scale_factor))
    new_h = max(th, int(orig_h * scale_factor))
    
    # Optimization: Downscale for face detection to drastically improve speed
    track_w = 360
    track_h = int(new_h * (360.0 / new_w))
    
    # Need YuNet detector initialized with the tracking resolution
    detector = cv2.FaceDetectorYN.create(YUNET_MODEL_PATH, "", (track_w, track_h), score_threshold=0.35)
    
    # Tracking variables
    current_x = new_w / 2.0  # start at center
    deadzone = 0.03 * new_w
    ema_alpha = 0.1
    
    encoder_args = get_best_encoder()
    cap.release() # Release outer cap, since process_frames creates its own
    
    def run_ffmpeg(enc_args):
        from services.ffmpeg import FFMPEG_CMD
        ffmpeg_cmd = [
            FFMPEG_CMD, "-y", "-loglevel", "error", "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{tw}x{th}", "-pix_fmt", "bgr24", "-r", str(fps),
            "-i", "-"
        ] + enc_args + ["-pix_fmt", "yuv420p", output_path]
        
        return subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    process = run_ffmpeg(encoder_args)
    
    def process_frames(proc):
        nonlocal current_x
        # Create a new VideoCapture for this process run to ensure safe retries
        cap_inner = cv2.VideoCapture(input_path)
        cap_inner.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        
        frame_count = start_frame
        while frame_count <= end_frame:
            ret, frame = cap_inner.read()
            if not ret or frame is None:
                break
                
            frame_resized = cv2.resize(frame, (new_w, new_h))
            
            # Optimization: Detect faces on downscaled frame
            frame_track = cv2.resize(frame, (track_w, track_h))
            detector.setInputSize((track_w, track_h))
            _, faces = detector.detect(frame_track)
            
            if faces is not None and len(faces) > 0:
                scale_up = new_w / float(track_w)
                
                # Prevent jumping between faces: heavily penalize faces that are far from our current tracked position
                def face_weight(f):
                    f_w = f[2] * scale_up
                    f_center = (f[0] + f[2] / 2.0) * scale_up
                    distance_penalty = abs(f_center - current_x) * 2.0
                    return f_w - distance_penalty
                    
                main_face = sorted(faces, key=face_weight, reverse=True)[0]
                face_center_x = (main_face[0] + main_face[2] / 2.0) * scale_up
                
                # Apply 3% deadzone & EMA
                if abs(face_center_x - current_x) > deadzone:
                    current_x = ema_alpha * face_center_x + (1.0 - ema_alpha) * current_x
            
            # Calculate safe crop box
            crop_x = int(current_x - tw / 2.0)
            crop_x = max(0, min(new_w - tw, crop_x))
            crop_y = int((new_h - th) / 2.0)
            crop_y = max(0, min(new_h - th, crop_y))
            
            cropped_frame = frame_resized[crop_y:crop_y+th, crop_x:crop_x+tw]
            if cropped_frame.shape[0] != th or cropped_frame.shape[1] != tw:
                cropped_frame = cv2.resize(cropped_frame, (tw, th))
                
            try:
                proc.stdin.write(cropped_frame.tobytes())
            except (OSError, BrokenPipeError) as e:
                print(f"[FaceTracker Warning] Pipe write stopped: {e}")
                break
            frame_count += 1
            
        cap_inner.release()
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            _, stderr_data = proc.communicate()
        except OSError as e:
            print(f"[FaceTracker Warning] communicate() threw OSError: {e}")
            stderr_data = b""
        
        return proc.returncode, stderr_data

    # First attempt (possibly NVENC)
    ret_code, stderr_data = await asyncio.to_thread(process_frames, process)
    if ret_code != 0 and stderr_data:
        safe_err = stderr_data.decode('utf-8', errors='ignore').replace('\x00', '').strip()
        print(f"[FaceTracker FFmpeg Error (1st attempt)]: {safe_err[-500:]}", flush=True)
        
        # Fallback to libx264 if NVENC failed
        if "h264_nvenc" in encoder_args:
            print("[FaceTracker] NVENC failed. Retrying with CPU (libx264)...")
            fallback_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]
            process_fb = run_ffmpeg(fallback_args)
            # We need to re-open the VideoCapture for the fallback pass
            ret_code, stderr_data = await asyncio.to_thread(process_frames, process_fb)
            if ret_code != 0 and stderr_data:
                safe_err = stderr_data.decode('utf-8', errors='ignore').replace('\x00', '').strip()
                print(f"[FaceTracker FFmpeg Error (Fallback)]: {safe_err[-500:]}", flush=True)
                
    return ret_code == 0
