import httpx
from mcp_server.mcp_instance import mcp
from mcp_server.utils import _require_env_vars


@mcp.tool(
    description="Поиск в Google. Args: query - запрос, start - сдвиг (1 для первой страницы, 11 для второй и т.д.). Используй start для пагинации, если на первой странице нет ничего полезного.")
async def google_search(query: str, start: int = 1, num_results: int = 10) -> str:
    """
    Выполняет поиск в Google с поддержкой пагинации.
    """
    env = _require_env_vars(["GOOGLE_API_KEY", "GOOGLE_CSE_ID"])

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": env["GOOGLE_API_KEY"],
        "cx": env["GOOGLE_CSE_ID"],
        "q": query,
        "num": min(num_results, 10),
        "start": start  # <--- ДОБАВИЛИ ПАРАМЕТР
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            # Обработка 429 ошибки (лимиты) или других
            if response.status_code != 200:
                return f"Ошибка Google API: {response.status_code}. Возможно, лимит запросов исчерпан."

            data = response.json()

        if "items" not in data:
            return "По вашему запросу ничего не найдено. Попробуйте переформулировать запрос."

        results_text = [f"--- РЕЗУЛЬТАТЫ ПОИСКА (Страница {(start - 1) // 10 + 1}) ---"]
        for i, item in enumerate(data["items"], start):
            title = item.get("title", "Нет заголовка")
            link = item.get("link", "#")
            snippet = item.get("snippet", "Нет описания")
            results_text.append(f"{i}. [{title}]({link})\n   {snippet}\n")

        return "\n".join(results_text)

    except Exception as e:
        return f"Ошибка поиска: {str(e)}"