import requests
import json
import time
import sys

url = "http://127.0.0.1:8001/api/v1/clips"
payload = {
    "youtube_urls": ["https://www.youtube.com/watch?v=jNQXAC9IVRw"], # Me at the zoo (very short video)
    "clip_count": 1,
    "enable_subtitles": True,
    "layout_mode": "auto",
    "auto_reframe": True
}

print("Mengirimkan MOCK JOB ke AutoClipWeb...")
try:
    response = requests.post(url, json=payload, timeout=10)
    print("Status Pengiriman:", response.status_code)
except requests.exceptions.ConnectionError:
    print("Gagal terhubung. Pastikan server AutoClipWeb (python main.py) sudah berjalan di port 8001.")
    sys.exit(1)

if response.status_code == 202:
    data = response.json()
    job_ids = data.get("job_ids", [])
    if not job_ids:
        job_id = data.get("job_id")
        job_ids = [job_id] if job_id else []
        
    for jid in job_ids:
        print(f"\n[JOB ID: {jid}] - Mulai memantau proses end-to-end...")
        while True:
            try:
                res = requests.get(f"http://127.0.0.1:8001/api/v1/clips/{jid}", timeout=5)
                if res.status_code == 200:
                    job_data = res.json()
                    status = job_data.get("status")
                    prog = job_data.get("progress_percentage")
                    msg = job_data.get("current_step_message")
                    
                    print(f"Status: {status} | Progress: {prog}% | Msg: {msg}")
                    
                    if status in ["COMPLETED", "FAILED"]:
                        print(f"\n✅ Proses Selesai! Status akhir: {status}")
                        if status == "FAILED":
                            print("❌ Error Log:")
                            print(job_data.get("error_log"))
                        elif status == "COMPLETED":
                            clips = job_data.get("output_video_path")
                            print(f"🎉 Klip berhasil dibuat! Path: {clips}")
                        break
                else:
                    print(f"Gagal mengambil status, HTTP {res.status_code}")
                    break
            except Exception as e:
                print(f"Koneksi terputus saat memantau: {e}")
                break
            
            time.sleep(3)
else:
    print("Gagal membuat job:", response.text)
