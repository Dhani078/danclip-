import os
import re
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def strip_emojis(text: str) -> str:
    """Strips emojis and non-ASCII characters to avoid missing font square box artifacts (□)."""
    if not text:
        return ""
    # Keep standard alphanumeric, Indonesian characters, punctuation
    cleaned = re.sub(r'[^\w\s\d.,!?:;\-\'\"]', '', text)
    return ' '.join(cleaned.split()).strip()

def generate_viral_thumbnail(
    video_path: str,
    output_jpg_path: str,
    hook_title: str,
    viral_score: int = 90,
    target_w: int = 1080,
    target_h: int = 1920
) -> str:
    """
    Generates a high-impact viral cover image (.jpg) for TikTok/Reels/Shorts.
    Extracts keyframe image, crops to 9:16 vertical, adds gradient contrast overlays,
    and draws bold viral hook title. Does NOT include internal viral score badges.
    """
    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        
        # Seek to frame at 2.5 seconds for optimal speaker expression
        target_frame = int(2.5 * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        
        if not ret or frame is None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            
        cap.release()
        
        if not ret or frame is None:
            # Blank fallback frame if video fails
            frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            
        # Convert BGR (OpenCV) to RGB (PIL)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        
        # Crop & Resize to 9:16 aspect ratio (1080x1920)
        img_w, img_h = img.size
        target_ratio = target_w / float(target_h)
        current_ratio = img_w / float(img_h)
        
        if current_ratio > target_ratio:
            new_w = int(img_h * target_ratio)
            left = (img_w - new_w) // 2
            img = img.crop((left, 0, left + new_w, img_h))
        else:
            new_h = int(img_w / target_ratio)
            top = (img_h - new_h) // 2
            img = img.crop((0, top, img_w, top + new_h))
            
        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        # Create dark gradient overlays at top & bottom for high text readability
        draw = ImageDraw.Draw(img, "RGBA")
        
        # Top gradient box (deeper contrast for top headline)
        for y in range(650):
            alpha = int(220 * (1.0 - y / 650.0))
            draw.line([(0, y), (target_w, y)], fill=(0, 0, 0, alpha))
            
        # Bottom vignette gradient
        for y in range(target_h - 350, target_h):
            prog = (y - (target_h - 350)) / 350.0
            alpha = int(180 * prog)
            draw.line([(0, y), (target_w, y)], fill=(0, 0, 0, alpha))
            
        # Fonts setup
        try:
            # Try Impact or Arial Bold for ultra-clean headline rendering
            font_title = ImageFont.truetype("impact.ttf", 76)
        except:
            font_title = ImageFont.load_default()
            
        # Main Viral Hook Title Banner (Placed at upper center, y=140)
        clean_hook = strip_emojis(hook_title)
        if not clean_hook:
            clean_hook = "BUDAK CORPORATE BISA MATI SYAHID?"
            
        words = clean_hook.upper().split()
        lines = []
        curr_line = ""
        for w in words:
            test_line = f"{curr_line} {w}".strip()
            bbox = font_title.getbbox(test_line)
            line_w = (bbox[2] - bbox[0]) if bbox else len(test_line) * 40
            if line_w > target_w - 120:
                if curr_line:
                    lines.append(curr_line)
                curr_line = w
            else:
                curr_line = test_line
        if curr_line:
            lines.append(curr_line)
            
        # Draw Title Box Background & Text with high contrast
        start_y = 150
        line_height = 88
        box_padding = 28
        
        for i, line in enumerate(lines):
            y_pos = start_y + (i * (line_height + 18))
            bbox = font_title.getbbox(line)
            text_w = (bbox[2] - bbox[0]) if bbox else len(line) * 40
            text_h = (bbox[3] - bbox[1]) if bbox else 70
            x_pos = (target_w - text_w) // 2
            
            # Alternate Vivid Colors for maximum TikTok eye-catchiness
            if i % 3 == 0:
                bg_color = (250, 204, 21, 245)   # Vivid Yellow
                text_color = (15, 23, 42)        # Dark Charcoal
                stroke_color = (255, 255, 255)
            elif i % 3 == 1:
                bg_color = (15, 23, 42, 245)    # Dark Charcoal
                text_color = (255, 255, 255)     # Bright White
                stroke_color = (250, 204, 21)
            else:
                bg_color = (225, 29, 72, 245)    # Crimson Red
                text_color = (255, 255, 255)     # Bright White
                stroke_color = (0, 0, 0)
            
            # Rounded background banner box
            box_left = max(36, x_pos - box_padding)
            box_right = min(target_w - 36, x_pos + text_w + box_padding)
            box_top = y_pos - 10
            box_bottom = y_pos + text_h + 22
            
            draw.rounded_rectangle(
                [box_left, box_top, box_right, box_bottom],
                radius=16,
                fill=bg_color,
                outline=(0, 0, 0, 200),
                width=3
            )
            # Crisp text with stroke
            draw.text((x_pos, y_pos), line, fill=text_color, font=font_title, stroke_width=2, stroke_fill=stroke_color)
            
        # Save output image
        os.makedirs(os.path.dirname(output_jpg_path), exist_ok=True)
        img.convert("RGB").save(output_jpg_path, "JPEG", quality=95)
        print(f"[Thumbnail Generator] Created clean viral cover: {output_jpg_path}")
        return output_jpg_path
        
    except Exception as e:
        print(f"[Thumbnail Generator Error] {e}")
        return None
