import os

from openai import OpenAI

api_key = "ODg0MDA2MmQtYWIxNS00NmNiLTkxMTQtZTdmYWNiM2RiNjJi.fd712535ba0483156093833cfa8d1b73"
url = "https://foundation-models.api.cloud.ru/v1"

client = OpenAI(
    api_key=api_key,
    base_url=url
)

response = client.chat.completions.create(
    model="ai-sage/GigaChat3-10B-A1.8B",
    max_tokens=2500,
    temperature=0.5,
    presence_penalty=0,
    top_p=0.95,
    messages=[
        {
            "role": "user",
            "content":"Как написать хороший код?"
        }
    ]
)

print(response.choices[0].message.content)