from utils.timestamp import parse_timestamp, validate_clips

def test_parse_timestamp():
    assert parse_timestamp("5:03") == 303.0
    assert parse_timestamp("01:05:03") == 3903.0
    assert parse_timestamp("63") == 63.0
    assert parse_timestamp("10.5") == 10.5
    assert parse_timestamp("0:10") == 10.0
    assert parse_timestamp(" 01:00 ") == 60.0
    
    for bad in ["abc", "", None, "12:abc"]:
        try:
            parse_timestamp(bad)
            assert False, f"Should have raised ValueError for {bad}"
        except ValueError:
            pass

def test_validate_clips():
    clips = [
        {"start_time": "0:00", "end_time": "0:30", "viral_score": 90}, # Valid
        {"start_time": "0:10", "end_time": "0:25", "viral_score": 95}, # Valid, but overlaps with #1 >50%. Should override #1 or be overridden?
        # Actually duration of #2 is 15s. Overlap is 15s. 15s / 15s = 1.0 > 0.5. Since #2 has 95 score, #2 kept, #1 drops if #1 overlap > 50%.
        # Wait, #1 is 30s. Overlap is 15s. 15s / 30s = 0.5. Is it > 0.5? No, it's == 0.5.
        {"start_time": "0:00", "end_time": "0:05", "viral_score": 100}, # Too short (<10s)
        {"start_time": "1:00", "end_time": "4:00", "viral_score": 80}, # Too long (>120s)
        {"start_time": "2:00", "end_time": "1:00", "viral_score": 85}, # start > end
    ]
    
    # 2 overlaps with 1 but 2 has higher score. Let's make overlap definitely > 50%
    clips[0]["end_time"] = "0:20" # duration 20s. Overlap 10s (0:10 to 0:20). 10/20 = 0.5. Still not >0.5.
    clips[0]["end_time"] = "0:15" # duration 15s. Overlap 5s. 5/15 = 0.33.
    
    # Let's just create an obvious overlap test
    clips = [
        {"start_time": "0:00", "end_time": "0:30", "viral_score": 80},
        {"start_time": "0:05", "end_time": "0:25", "viral_score": 95}, # duration 20s. Overlap with above is 20s. 20/20 > 0.5. 20/30 > 0.5. So score 95 wins.
    ]
    res = validate_clips(clips, 1000)
    assert len(res) == 1
    assert res[0]["viral_score"] == 95
    
    # Test clamp to video_duration
    clips = [
        {"start_time": "9:00", "end_time": "9:40", "viral_score": 80}, # duration 40s
    ]
    res = validate_clips(clips, 560) # 9:20 is the end
    assert len(res) == 1
    assert res[0]["end_time"] == "09:20"
    
    # Test clamp makes it too short
    clips = [
        {"start_time": "9:15", "end_time": "9:40", "viral_score": 80},
    ]
    res = validate_clips(clips, 560) # 9:15 to 9:20 is 5s < 10s
    assert len(res) == 0

if __name__ == "__main__":
    test_parse_timestamp()
    test_validate_clips()
    print("All tests passed!")
