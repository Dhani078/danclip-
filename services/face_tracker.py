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
