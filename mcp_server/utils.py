import os
from typing import Dict, Any, Callable, List
from mcp.shared.exceptions import McpError, ErrorData
from mcp.types import TextContent, EmbeddedResource, ImageContent

# Alias для удобства (Правило 4.3)
ToolResult = list[TextContent | EmbeddedResource | ImageContent]

def _require_env_vars(names: list[str]) -> dict[str, str]:
    """
    Проверяет наличие обязательных переменных окружения.
    Raises:
        McpError: Если отсутствуют обязательные переменные
    """
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        from mcp.shared.exceptions import McpError, ErrorData
        raise McpError(
            ErrorData(
                code=-32602,
                message="Отсутствуют обязательные переменные окружения: " + ", ".join(missing)
            )
        )
    return {n: os.getenv(n, "") for n in names}


def tool_schema(schema: Dict[str, Any]) -> Callable:
    """
    Декоратор для явного определения схемы инструмента (JSON Schema).
    Используется для переопределения автоматической генерации схемы на основе Pydantic.

    Сохраняет схему в атрибуте `_tool_schema` функции и обновляет её `__doc__`.
    """

    def decorator(func: Callable) -> Callable:
        # Прикрепляем схему к функции, чтобы сервер мог её прочитать
        setattr(func, "_tool_schema", schema)

        # Если в схеме есть имя, пытаемся обновить имя функции (опционально)
        if "name" in schema:
            try:
                func.__name__ = schema["name"]
            except AttributeError:
                pass

        # Обновляем docstring функции из описания схемы
        # Это важно, так как многие MCP-библиотеки читают description из docstring
        if "description" in schema:
            func.__doc__ = schema["description"]

        return func

    return decorator
