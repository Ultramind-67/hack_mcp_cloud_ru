import os
from typing import Dict, Any, Callable, List
from mcp.types import TextContent, EmbeddedResource, ImageContent
from mcp.shared.exceptions import McpError, ErrorData

# ✅ Стандарт 4.3: Определяем тип ToolResult
ToolResult = list[TextContent | EmbeddedResource | ImageContent]

def _require_env_vars(names: List[str]) -> Dict[str, str]:
    """
    Проверяет наличие обязательных переменных окружения.
    Бросает стандартный McpError, если чего-то нет.
    """
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        # ✅ Стандарт 7.1: Использование McpError
        raise McpError(
            ErrorData(
                code=-32602, # Invalid params
                message=f"Отсутствуют обязательные переменные окружения: {', '.join(missing)}"
            )
        )
    return {n: os.getenv(n, "") for n in names}

# Оставляем ваш декоратор (он полезен, хоть и не по стандарту, но не мешает)
def tool_schema(schema: Dict[str, Any]) -> Callable:
    def decorator(func: Callable) -> Callable:
        setattr(func, "_tool_schema", schema)
        if "name" in schema:
            try: func.__name__ = schema["name"]
            except AttributeError: pass
        if "description" in schema:
            func.__doc__ = schema["description"]
        return func
    return decorator