import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("No API Key found")
    exit(1)

client = genai.Client(api_key=api_key)

print("Available Models:")
for m in client.models.list():
    print(m.name)
