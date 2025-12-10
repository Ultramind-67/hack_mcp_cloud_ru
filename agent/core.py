# agent/core.py
import json
import re
import os
import asyncio
from dotenv import load_dotenv

# MCP Imports
from mcp import ClientSession
from mcp.client.sse import sse_client

try:
    from .llm_client import get_client
except ImportError:
    from llm_client import get_client

load_dotenv()

SYSTEM_PROMPT = (
    "Ты — профессиональный менеджер по закупкам. Твоя цель: найти поставщиков, проанализировать их и составить отчет.\n"
    "Твой инструмент — папка `suppliers` и `exports`.\n\n"
    "АЛГОРИТМ:\n"
    "1. Поиск: Используй `create_supplier_profiles` (он ищет, читает сайты и сохраняет .md).\n"
    "2. Анализ: Если просят таблицу, сначала собери данные, потом сделай `create_suppliers_top_csv`.\n"
    "3. Ответ: Всегда давай краткую выжимку и говори, какие файлы были созданы.\n\n"
    "ВАЖНО: Если ты создал CSV, обязательно скажи об этом пользователю."
)


class AgentClient:
    def __init__(self):
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.llm = get_client()

    def clean_content(self, text: str) -> str:
        if not text: return ""
        return text.replace("<|message_sep|>", "").replace("function call", "").strip()

    async def process_message(self, user_message, status_callback, mcp_url="http://127.0.0.1:8000/sse"):
        """
        Полный цикл ReAct с поддержкой Streaming.
        """
        self.history.append({"role": "user", "content": user_message})
        final_answer = ""

        status_callback("🔌 Подключаюсь к инструментам...")

        try:
            async with sse_client(url=mcp_url) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()

                    tools_list = await session.list_tools()
                    openai_tools = [{
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.inputSchema
                        }
                    } for t in tools_list.tools]

                    # ReAct Loop (до 15 шагов)
                    for step in range(15):
                        status_callback(f"🧠 Думаю (шаг {step + 1})...")

                        # --- ИЗМЕНЕНИЕ: STREAMING ЗАПРОС ---
                        stream = await self.llm.chat.completions.create(
                            model="Qwen/Qwen3-235B-A22B-Instruct-2507",
                            messages=self.history,
                            tools=openai_tools if openai_tools else None,
                            tool_choice="auto" if openai_tools else None,
                            stream=True  # <--- ВКЛЮЧАЕМ ПОТОК
                        )

                        full_content = ""
                        tool_calls_chunks = []

                        # Читаем поток по кусочкам
                        async for chunk in stream:
                            delta = chunk.choices[0].delta

                            # 1. Если идет текст
                            if delta.content:
                                full_content += delta.content
                                # Обновляем статус каждые 50 символов, чтобы было видно, что бот жив
                                if len(full_content) % 50 == 0:
                                    status_callback(f"📝 Генерирую ответ... ({len(full_content)} симв.)")

                            # 2. Если идут вызовы инструментов (OpenAI формат)
                            if delta.tool_calls:
                                for tool_call in delta.tool_calls:
                                    if len(tool_calls_chunks) <= tool_call.index:
                                        tool_calls_chunks.append({"id": "", "function": {"name": "", "arguments": ""}})

                                    tc = tool_calls_chunks[tool_call.index]
                                    if tool_call.id: tc["id"] += tool_call.id
                                    if tool_call.function.name: tc["function"]["name"] += tool_call.function.name
                                    if tool_call.function.arguments: tc["function"][
                                        "arguments"] += tool_call.function.arguments

                        # Сборка ответа после завершения потока
                        content = self.clean_content(full_content)

                        # Преобразуем накопленные чанки тулов в объекты
                        tool_calls = []
                        for tc in tool_calls_chunks:
                            tool_calls.append(type('obj', (object,), {
                                'id': tc['id'],
                                'function': type('func', (object,), {
                                    'name': tc['function']['name'],
                                    'arguments': tc['function']['arguments']
                                })
                            }))
                        if not tool_calls: tool_calls = None

                        # Создаем объект сообщения для истории (так как streaming не возвращает message object)
                        response_msg = type('obj', (object,), {
                            'content': content,
                            'tool_calls': tool_calls,
                            'role': 'assistant'
                        })

                        # -----------------------------------

                        # Парсинг кастомных форматов (Qwen XML / ReAct)
                        custom_tool_data = self._parse_custom_formats(content)

                        # Если инструментов нет — это финал
                        if not tool_calls and not custom_tool_data:
                            final_answer = content
                            self.history.append({"role": "assistant", "content": content})
                            break

                        # Сохраняем "мысль"
                        # Для истории нужно сохранить tool_calls корректно (как dict, если это API OpenAI)
                        # Но для упрощения сохраняем как текст + custom parsing, так как модель может путаться
                        if tool_calls:
                            # Конвертируем обратно в dict для совместимости с OpenAI API при следующем запросе
                            self.history.append({
                                "role": "assistant",
                                "content": content,
                                "tool_calls": [
                                    {
                                        "id": tc.id,
                                        "type": "function",
                                        "function": {
                                            "name": tc.function.name,
                                            "arguments": tc.function.arguments
                                        }
                                    } for tc in tool_calls
                                ]
                            })
                        else:
                            self.history.append({"role": "assistant", "content": content})

                        # Подготовка инструментов
                        to_execute = []
                        if tool_calls:
                            to_execute = tool_calls
                        elif custom_tool_data:
                            class FakeTool:
                                def __init__(self, n, a):
                                    self.id = "custom"
                                    self.function = type('o', (object,), {'name': n, 'arguments': json.dumps(a)})

                            to_execute = [FakeTool(custom_tool_data['name'], custom_tool_data['arguments'])]

                        # Выполнение
                        for tool in to_execute:
                            name = tool.function.name
                            args_str = tool.function.arguments
                            try:
                                args = json.loads(args_str) if isinstance(args_str, str) else args_str
                            except:
                                args = {}

                            status_callback(f"🛠 Использую инструмент: {name}...")

                            try:
                                result = await session.call_tool(name, arguments=args)
                                res_text = result.content[0].text
                                if len(res_text) > 4000: res_text = res_text[:4000] + "...(cut)"
                            except Exception as e:
                                res_text = f"Error: {e}"

                            self.history.append({
                                "role": "tool",
                                "tool_call_id": getattr(tool, 'id', 'custom'),
                                "name": name,
                                "content": res_text
                            })

        except Exception as e:
            return f"❌ Ошибка соединения или модели: {e}"

        return final_answer

    def _parse_custom_formats(self, content):
        """Парсинг ReAct, XML, Raw JSON"""
        if not content: return None
        # ReAct
        act = re.search(r'Action:\s*([a-zA-Z0-9_]+)', content)
        arg = re.search(r'Arguments:\s*(\{.*?\})', content, re.DOTALL)
        if act and arg:
            try:
                return {"name": act.group(1).strip(), "arguments": json.loads(arg.group(1))}
            except:
                pass
        # XML
        xml = re.search(r'<tool_call>(.*?)</tool_call>', content, re.DOTALL)
        if xml:
            try:
                return json.loads(xml.group(1))
            except:
                pass
        # Raw JSON
        if "json" in content.lower() and "{" in content:
            try:
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                    if "name" in data: return data
            except:
                pass
        return None