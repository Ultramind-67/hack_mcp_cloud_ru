import os
import asyncio
import httpx
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()


async def test_search():
    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")

    print(f"🔑 API Key: {'***' + api_key[-4:] if api_key else 'НЕ НАЙДЕН'}")
    print(f"🔎 CSE ID: {cse_id if cse_id else 'НЕ НАЙДЕН'}")

    if not api_key or not cse_id:
        print("❌ Ошибка: Не заданы ключи в .env")
        return

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cse_id,
        "q": "курс биткоина к доллару",  # Тестовый запрос
        "num": 1
    }

    print("\n⏳ Отправка запроса в Google...")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)

            # Если код не 200, выводим ошибку
            if response.status_code != 200:
                print(f"❌ Ошибка API: {response.status_code}")
                print(response.text)
                return

            data = response.json()

            if "items" in data:
                first_result = data["items"][0]
                print("\n✅ УСПЕХ! Google работает.")
                print(f"Заголовок: {first_result.get('title')}")
                print(f"Ссылка: {first_result.get('link')}")
                print(f"Сниппет: {first_result.get('snippet')}")
            else:
                print(
                    "\n⚠️ Запрос прошел, но результатов нет. Проверьте настройки Search Engine (должен быть включен 'Search the entire web').")

    except Exception as e:
        print(f"❌ Сетевая ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(test_search())