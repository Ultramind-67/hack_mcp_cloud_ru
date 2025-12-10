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
    "Ты — дотошный аналитик данных. Твоя задача — собрать ПОЛНУЮ и ДОСТОВЕРНУЮ информацию.\n"
    "Ты работаешь в цикле: Мысль -> Действие -> Наблюдение.\n\n"
    "У тебя есть ФАЙЛОВАЯ СИСТЕМА (папка suppliers), где ты обязан вести досье на компании.\n\n"

    "=== ТВОИ РЕЖИМЫ РАБОТЫ ===\n\n"
    
    "РЕЖИМ 1: ПОИСК ПОСТАВЩИКОВ\n"
    "Если просят найти поставщиков, производителей или компании:\n"
    "1. НЕ используй обычный `google_search`.\n"
    "2. ИСПОЛЬЗУЙ `create_supplier_profiles` (query=...). Это создаст файлы .md с досье.\n"
    "3. В ответе пользователю напиши: 'Созданы профили для компаний: [список]'.\n\n"
    
    "РЕЖИМ 2: ПЕРЕПИСКА И КОНТЕКСТ\n"
    "Если ты пишешь письмо поставщику или анализируешь его ответ:\n"
    "1. Сначала найди его файл (через поиск или контекст).\n"
    "2. ИСПОЛЬЗУЙ `add_llm_interaction` для сохранения сути переписки в файл.\n"
    "3. Никогда не полагайся только на память диалога — всё важное пиши в файл!\n\n"
    
    "РЕЖИМ 3: ОБЩИЙ АНАЛИЗ\n"
    "Для обычных вопросов используй связку `google_search` -> `read_url` -> Ответ.\n\n"
    
    "ГЛАВНОЕ ПРАВИЛО: Если речь о конкретной компании-поставщике, результат должен лежать в .md"

    "ПРАВИЛА ИССЛЕДОВАНИЯ:\n"
    "1. ОЦЕНКА ВЫДАЧИ: После поиска (`google_search`) всегда оценивай результаты. "
    "Если они мусорные (SEO-статьи, форумы, реклама) — НЕ ЧИТАЙ ИХ. "
    "Вместо этого: либо иди на следующую страницу (`start=11`), либо ПЕРЕФОРМУЛИРУЙ запрос.\n"

    "2. СБОР ДАННЫХ: Твоя цель — найти первоисточники. "
    "Если нужны компании — ищи их официальные сайты. "
    "Если нужны цены — ищи прайс-листы.\n"

    "3. ЧТЕНИЕ: Используй `read_url` для глубокого анализа. Заголовков недостаточно!\n"

    "4. САМОКРИТИКА: Перед тем как выдать финальный ответ, спроси себя: "
    "'Достаточно ли у меня фактов для таблицы?'. Если нет — продолжай искать.\n\n"

    "ПРИМЕР ПЛОХОГО ПОВЕДЕНИЯ:\n"
    "- Нашел 1 ссылку, придумал остальное -> ПЛОХО.\n"
    "- Поискал 'разработка', нашел Reddit -> ПЛОХО.\n\n"

    "ПРИМЕР ХОРОШЕГО ПОВЕДЕНИЯ:\n"
    "- Поискал 'рейтинг веб-студий'. Нашел 10 ссылок.\n"
    "- Ссылки 1-3 — реклама. Ссылка 4 — рейтинг Tagline. Читаю её (`read_url`).\n"
    "- В рейтинге нашел названия компаний. Ищу теперь конкретно их сайты.\n"
    "- Читаю сайты, собираю цены.\n"
    "- Данные собраны. Формирую таблицу.\n"
    "- Экспортирую таблицу в CSV (`create_suppliers_top_csv`)."
    "- Сохраняю данные по поставщикам в md формате (generate_supplier_profile)."
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