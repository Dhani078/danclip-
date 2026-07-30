import sqlite3

def check_db(db_path):
    print(f"--- Checking {db_path} ---")
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = c.fetchall()
        print(f"Tables: {tables}")
        
        if ('video_jobs',) in tables:
            c.execute("SELECT id, status, current_step_message, created_at, error_log FROM video_jobs ORDER BY created_at DESC LIMIT 5;")
            rows = c.fetchall()
            print("\nRecent 5 Jobs:")
            for row in rows:
                print(f"ID: {row[0]}")
                print(f"Status: {row[1]}")
                print(f"Message: {row[2]}")
                print(f"Created: {row[3]}")
                if row[4]:
                    print(f"Error (truncated): {row[4][:100]}...")
                print("-" * 20)
        else:
            print("Table 'video_jobs' not found.")
        conn.close()
    except Exception as e:
        print(f"Error reading DB: {e}")

if __name__ == '__main__':
    import os
    if os.path.exists('clipper.db'):
        check_db('clipper.db')
    if os.path.exists('clipper_backup.db'):
        check_db('clipper_backup.db')
