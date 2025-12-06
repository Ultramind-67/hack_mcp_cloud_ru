import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

def get_client():
    key = os.environ.get("API_KEY", "").replace("Bearer ", "").strip()
    return AsyncOpenAI(
        api_key=key,
        base_url="https://foundation-models.api.cloud.ru/v1",
        default_headers={"Authorization": f"Bearer {key}"}
    )