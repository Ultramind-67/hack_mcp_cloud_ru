from fastmcp import Context
from pydantic import Field
from mcp_server.mcp_instance import mcp

@mcp.tool(
    name="my_business_tool",
    description="Получает информацию о компании по ИНН. Возвращает название, статус и рейтинг надежности."
)
async def my_business_tool(
    inn: str = Field(..., description="ИНН компании (строка цифр)"),
    ctx: Context = None
) -> str:
    # Здесь в реальности был бы запрос к API (DaData, API ФНС и т.д.)
    # Для теста мы сделаем имитацию (MOCK)

    await ctx.info(f"🔍 Ищу информацию по ИНН: {inn}")

    # Имитация базы данных
    mock_db = {
        "7707083893": {"name": "ПАО СБЕРБАНК", "status": "ACTIVE", "rating": "HIGH", "revenue": "Huge"},
        "1234567890": {"name": "ООО РОГА И КОПЫТА", "status": "BANKRUPT", "rating": "LOW", "revenue": "0"}
    }

    result = mock_db.get(inn, {"error": "Компания не найдена"})
    return str(result)