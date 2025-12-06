# Business AI Agent (MCP Architecture)

Проект реализует бизнес-ассистента на базе **Cloud.ru Evolution (GigaChat)**, использующего протокол **MCP (Model Context Protocol)** для интеграции с внешними инструментами.

## 🏗 Архитектура

Система разделена на два независимых компонента:

1.  **MCP Server ("Руки")**:
    *   Работает на `fastmcp`.
    *   Предоставляет инструменты (Tools) для LLM.
    *   Запускается как веб-сервер (SSE transport).
    *   Автоматически подхватывает новые инструменты из папки `tools/`.

2.  **AI Agent ("Мозг")**:
    *   Клиент на Python (`AsyncOpenAI` + `mcp` SDK).
    *   Управляет диалогом и контекстом.
    *   Парсит ответы LLM (включая специфичный формат GigaChat) и вызывает инструменты на сервере.

### Структура проекта

```text
.
├── agent/                 # Клиентская часть (LLM)
│   ├── main.py            # Точка входа агента
│   └── llm_client.py      # Настройки подключения к Cloud.ru
├── mcp_server/            # Серверная часть (Инструменты)
│   ├── server.py          # Точка входа сервера
│   ├── mcp_instance.py    # Singleton инстанс FastMCP
│   └── tools/             # 📂 СЮДА ДОБАВЛЯТЬ НОВЫЕ ИНСТРУМЕНТЫ
│       ├── __init__.py
│       └── teamplate.py
├── .env                   # API ключи и настройки
└── pyproject.toml         # Зависимости
```

---

## 🚀 Установка и Настройка

### 1. Подготовка окружения
Требуется Python 3.10+ (рекомендуется 3.12).

```bash
# Создание venv (Windows)
python -m venv .venv
.venv\Scripts\activate

# Установка зависимостей
pip install fastmcp mcp openai python-dotenv uvicorn
```

### 2. Настройка ключей
Создайте файл `.env` в корне проекта (используйте `.env.example` как шаблон):

```ini
# Ключ от Cloud.ru Evolution / GigaChat
# Копируйте только Secret (без слова Bearer, скрипт добавит его сам)
API_KEY=AQVN...ваши_символы...

# Настройки сервера (опционально)
PORT=8000
HOST=0.0.0.0
```

---

## ▶️ Запуск

Для работы системы нужно **два** терминала. Запускать команды строго из **корня проекта**.

### Терминал 1: Запуск сервера (MCP)
```bash
python -m mcp_server.server
```
*Ожидаемый вывод:* `🚀 MCP Server running on http://0.0.0.0:8000/sse`

### Терминал 2: Запуск агента (Client)
```bash
python -m agent.main
```
*Ожидаемый вывод:* `✅ Подключено к MCP-серверу!`

---

## 🛠 Разработка (Для команды)

### Как добавить новый инструмент?
Не нужно трогать `server.py`. Просто создайте новый файл в папке `mcp_server/tools/`.

**Пример (`mcp_server/tools/crm.py`):**

```python
from fastmcp import Context
from pydantic import Field
from mcp_server.mcp_instance import mcp

@mcp.tool(name="get_client_data", description="Поиск клиента в CRM")
async def get_client_data(
    phone: str = Field(..., description="Телефон клиента"),
    ctx: Context = None
) -> str:
    await ctx.info(f"🔍 Ищу клиента: {phone}")
    # Ваша логика...
    return "Данные клиента..."
```