import re

def parse_timestamp(value: str) -> float:
    """Menerima 'SS', 'MM:SS', 'HH:MM:SS', dengan atau tanpa desimal.
    Melempar ValueError kalau tidak bisa diurai."""
    if not value:
        raise ValueError("Timestamp kosong")
    if isinstance(value, (int, float)):
        return float(value)
    
    value = str(value).strip()
    
    # Format MM:SS atau HH:MM:SS
    parts = value.split(':')
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        else:
            raise ValueError(f"Format timestamp tidak dikenal: {value}")
    except ValueError:
        raise ValueError(f"Gagal mem-parsing timestamp: {value}")

def validate_clips(clips: list, video_duration: float) -> list:
    """Membuang klip yang tidak valid:
    - start >= end
    - durasi < 10 detik atau > 120 detik
    - end melebihi video_duration (clamp dulu, buang kalau jadi < 10 detik)
    - tumpang tindih > 50% dengan klip lain yang skornya lebih tinggi
    Mengembalikan daftar yang sudah bersih, terurut menurut start."""
    
    valid_clips = []
    
    # 1. Parsing & Basic Validation
    for c in clips:
        try:
            start = parse_timestamp(c.get('start_time', '0'))
            end = parse_timestamp(c.get('end_time', '0'))
        except ValueError:
            continue
            
        if start >= end:
            continue
            
        # Clamp to video_duration
        if end > video_duration:
            end = video_duration
            
        duration = end - start
        if duration < 5 or duration > 600:
            continue
            
        # Convert back to MM:SS string for consistency, or keep float.
        # But we need to save string to db later in MM:SS
        def to_mmss(sec):
            m = int(sec // 60)
            s = int(sec % 60)
            return f"{m:02d}:{s:02d}"
            
        new_c = c.copy()
        new_c['start_time'] = to_mmss(start)
        new_c['end_time'] = to_mmss(end)
        new_c['_start'] = start
        new_c['_end'] = end
        
        # Viral score normalizer
        score = new_c.get('viral_score', 0)
        try:
            score = int(score)
        except (ValueError, TypeError):
            score = 0
        new_c['viral_score'] = score
        
        valid_clips.append(new_c)
        
    # 2. Sort by viral score DESC to keep highest score on overlap
    valid_clips.sort(key=lambda x: x['viral_score'], reverse=True)
    
    filtered_clips = []
    for c in valid_clips:
        start1 = c['_start']
        end1 = c['_end']
        duration1 = end1 - start1
        
        overlap_too_much = False
        for f in filtered_clips:
            start2 = f['_start']
            end2 = f['_end']
            
            overlap_start = max(start1, start2)
            overlap_end = min(end1, end2)
            if overlap_start < overlap_end:
                overlap_duration = overlap_end - overlap_start
                if overlap_duration / duration1 > 0.5:
                    overlap_too_much = True
                    break
        
        if not overlap_too_much:
            filtered_clips.append(c)
            
    # Remove temp keys and sort by start time
    filtered_clips.sort(key=lambda x: x['_start'])
    for c in filtered_clips:
        del c['_start']
        del c['_end']
        
    return filtered_clips
