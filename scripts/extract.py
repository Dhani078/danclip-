import json
with open(r'C:\Users\Anomali\.gemini\antigravity\brain\1e2ceb93-a1d2-4e2a-8632-c9941e9c2778\.system_generated\logs\overview.txt', 'r', encoding='utf-8') as f:
    for line in f:
        if '"step_index":12058' in line:
            data = json.loads(line)
            if 'content' in data:
                with open('audit_report.md', 'w', encoding='utf-8') as out:
                    out.write(data['content'])
