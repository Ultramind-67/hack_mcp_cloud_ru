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
    "Ты — профессиональный AI-менеджер по закупкам. Твоя цель: находить поставщиков, анализировать цены, проводить расчеты и вести переговоры.\n"
    "Ты работаешь в цикле: Мысль -> Действие -> Наблюдение.\n\n"

    "=== КАК РАБОТАЕТ ТВОЯ ПАМЯТЬ ===\n"
    "1. У тебя есть встроенная RAG-система. Когда ты используешь `find_suppliers` (начинай любой запрос на поиск поставщиков с него), "
    "система АВТОМАТИЧЕСКИ проверяет твои прошлые записи.\n"
    "2. Если инструмент говорит 'НАЙДЕНО В ЛОКАЛЬНОЙ БАЗЕ' — используй эти данные, не дублируй поиск.\n"
    "3. Когда ты сохраняешь профиль (`save_supplier_profile`), он АВТОМАТИЧЕСКИ запоминается. "
    "Тебе не нужно вызывать индексацию вручную.\n\n"
    
    "=== ТВОЙ ИНСТРУМЕНТАРИЙ ===\n"
    "1. 🗄 ФАЙЛОВАЯ СИСТЕМА: Ты обязан вести досье на компании в папке `suppliers`.\n"
    "2. 🧮 КАЛЬКУЛЯТОР: Используй инструмент `calculate` для любых вычислений.\n"
    "3. 📧 ПОЧТА: Используй `send_supplier_email` для запроса прайс-листов.\n"
    "4. 🌐 ПОИСК: `google_search`, `read_url`, `create_supplier_profiles`.\n"
    "5. 📊 ОТЧЕТЫ: `create_suppliers_top_csv`.\n\n"
    "6. 🧠 БАЗА ЗНАНИЙ: Если спрашивают о проекте или документации, используй `search_knowledge_base`. "
    "Если дают новый файл для изучения — сначала `index_document`.\n\n"

    "=== СЦЕНАРИИ РАБОТЫ ===\n\n"

    "СЦЕНАРИЙ 1: ПОИСК ПОСТАВЩИКОВ\n"
    "Если просят найти компании:\n"
    "1. ИСПОЛЬЗУЙ `create_supplier_profiles` (query=...). Это создаст файлы .md.\n"
    "2. В ответе перечисли найденные компании и скажи, что создал их досье.\n\n"

    "СЦЕНАРИЙ 2: АНАЛИЗ И РАСЧЕТЫ\n"
    "Если нужно сравнить цены, посчитать маржу, НДС или итоговую стоимость:\n"
    "1. Найди цены в файлах поставщиков или на сайте.\n"
    "2. СТРОГО ИСПОЛЬЗУЙ `calculate` для математики. Не считай в уме!\n"
    "3. Приведи расчеты в ответе.\n\n"

    "СЦЕНАРИЙ 3: КОММУНИКАЦИЯ (EMAIL)\n"
    "Если нужно запросить прайс или связаться с поставщиком:\n"
    "1. Найди email поставщика (в его .md файле или на сайте).\n"
    "2. Сформулируй деловое письмо.\n"
    "3. ИСПОЛЬЗУЙ `send_supplier_email`.\n"
    "4. После отправки ОБЯЗАТЕЛЬНО запиши факт отправки в досье через `add_llm_interaction`.\n\n"

    "СЦЕНАРИЙ 4: ИТОГОВЫЙ ОТЧЕТ\n"
    "1. Собери данные из всех досье (.md).\n"
    "2. Создай сводную таблицу.\n"
    "3. ЭКСПОРТИРУЙ через `create_suppliers_top_csv`.\n\n"
    
    "При создании CSV таблицы руководствуйся следующими данными:"
    "ФОРМАТ ТАБЛИЦЫ (7 столбцов, ЗАПОЛНИ ВСЕ СТРОКИ!):\n"
    "```\n"
    "| № | Название | Контакты | Сайт | Продукция | Регион | Описание |\n"
    "| 1 | [НАЗВАНИЕ КОМПАНИИ 1] | [ТЕЛЕФОН/EMAIL] | [URL САЙТА] | [ЧТО ПРОДАЕТ] | [ГОРОД/ОБЛАСТЬ] | [2-3 предложения о компании] |\n"
    "| 2 | [НАЗВАНИЕ КОМПАНИИ 2] | [ТЕЛЕФОН/EMAIL] | [URL САЙТА] | [ЧТО ПРОДАЕТ] | [ГОРОД/ОБЛАСТЬ] | [2-3 предложения о компании] |\n"
    "| 3 | [НАЗВАНИЕ КОМПАНИИ 3] | [ТЕЛЕФОН/EMAIL] | [URL САЙТА] | [ЧТО ПРОДАЕТ] | [ГОРОД/ОБЛАСТЬ] | [2-3 предложения о компании] |\n"
    "```\n\n"

    "ГЛАВНОЕ ПРАВИЛО: Твоя память ненадежна. Все важные данные (цены, контакты, история переписки) должны быть сохранены в файлы (.md) или таблицы (.csv)."
)


class AgentClient:
    def __init__(self):
        # История хранится здесь, поэтому контекст диалога не теряется при переподключении
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.llm = get_client()

    def clean_content(self, text: str) -> str:
        if not text: return ""
        return text.replace("<|message_sep|>", "").replace("function call", "").strip()

    async def process_message(self, user_message, status_callback, mcp_url="http://127.0.0.1:8000/sse"):
        """
        Полный цикл: Подключение -> Мысль -> Действие -> Ответ -> Отключение.
        Это гарантирует отсутствие ошибок генераторов.
        """
        self.history.append({"role": "user", "content": user_message})
        final_answer = ""

        status_callback("🔌 Подключаюсь к инструментам...")

        # ОТКРЫВАЕМ СОЕДИНЕНИЕ ТОЛЬКО НА ВРЕМЯ ОБРАБОТКИ ЗАПРОСА
        try:
            async with sse_client(url=mcp_url) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()

                    # Загружаем инструменты
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
                    for step in range(30):
                        status_callback(f"🧠 Думаю (шаг {step + 1})...")

                        # 1. Запрос к LLM
                        response = await self.llm.chat.completions.create(
                            model="Qwen/Qwen3-235B-A22B-Instruct-2507",  # Или GigaChat
                            messages=self.history,
                            tools=openai_tools if openai_tools else None,
                            tool_choice="auto" if openai_tools else None
                        )

                        response_msg = response.choices[0].message
                        content = self.clean_content(response_msg.content or "")
                        tool_calls = response_msg.tool_calls

                        # 2. Парсинг кастомных форматов
                        custom_tool_data = self._parse_custom_formats(content)

                        # 3. Если инструментов нет — это финал
                        if not tool_calls and not custom_tool_data:
                            final_answer = content
                            self.history.append(response_msg)
                            break

                        # 4. Сохраняем "мысль"
                        self.history.append(response_msg)

                        # 5. Подготовка инструментов
                        to_execute = []
                        if tool_calls:
                            to_execute = tool_calls
                        elif custom_tool_data:
                            class FakeTool:
                                def __init__(self, n, a):
                                    self.id = "custom"
                                    self.function = type('o', (object,), {'name': n, 'arguments': json.dumps(a)})

                            to_execute = [FakeTool(custom_tool_data['name'], custom_tool_data['arguments'])]

                        # 6. Выполнение
                        for tool in to_execute:
                            name = tool.function.name
                            args_str = tool.function.arguments
                            args = json.loads(args_str) if isinstance(args_str, str) else args_str

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
            return f"❌ Ошибка соединения с MCP сервером: {e}"

        return final_answer

    def _parse_custom_formats(self, content):
        """Парсинг ReAct, XML, Raw JSON"""
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
                        # Исправление: проверяем наличие 'arguments', чтобы не путать с данными компании
                        if "name" in data and "arguments" in data:
                            return data
                except:
                    pass