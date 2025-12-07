import httpx
from mcp_server.mcp_instance import mcp
from mcp_server.utils import _require_env_vars


@mcp.tool(
    description="Чтение содержимого веб-страницы через Jina Reader. Используй это, чтобы узнать цены, услуги и детали о компании с её сайта. Вход: url страницы.")
async def read_url(url: str) -> str:
    """
    Скачивает и очищает содержимое страницы, возвращая Markdown.
    """
    env = _require_env_vars(["JINA_API_KEY"])
    jina_url = f"https://r.jina.ai/{url}"

    headers = {
        "Authorization": f"Bearer {env['JINA_API_KEY']}",
        "X-Retain-Images": "none"  # Не грузим картинки, только текст
    }

    try:
        async with httpx.AsyncClient() as client:
            # Увеличиваем таймаут, так как Jina делает рендеринг
            response = await client.get(jina_url, headers=headers, timeout=20.0)

            if response.status_code != 200:
                return f"Ошибка чтения сайта: {response.status_code} {response.text}"

            text = response.text

            # Если текст слишком длинный, обрезаем, чтобы не перегрузить контекст модели
            # 8000 символов обычно достаточно для главной страницы
            if len(text) > 8000:
                text = text[:8000] + "\n...[текст обрезан]..."

            return f"--- CONTEND OF {url} ---\n{text}\n--- END OF CONTENT ---"

    except Exception as e:
        return f"Не удалось прочитать сайт {url}: {str(e)}"