import os
from fastmcp import Context
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