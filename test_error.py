from fastapi.testclient import TestClient
from main import app
import traceback

try:
    client = TestClient(app)
    response = client.get("/")
    print("STATUS:", response.status_code)
    print("BODY:", response.text)
except Exception as e:
    traceback.print_exc()
