import os
from dotenv import load_dotenv
import requests

load_dotenv()

api_key = os.getenv("TYPESAFE_API_KEY")

if not api_key:
    raise ValueError("TYPESAFE_API_KEY not found in .env")

url = "https://api.typesafe.ai/v1/models"

headers = {
    "Authorization": f"Bearer {api_key}"
}

response = requests.get(url, headers=headers, timeout=30)

print("status:", response.status_code)
print(response.text)