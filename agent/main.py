import asyncio
import json
import traceback
import re
from mcp import ClientSession
from mcp.client.sse import sse_client
from .llm_client import get_client
from dotenv import load_dotenv

load_dotenv()

# #не уверен что нужно
# from mcp.fastmcp import FastMCP
# from server.tools.suppliers import (
#     find_suppliers,
#     generate_supplier_profile,
#     save_supplier_profile,
#     add_llm_interaction,
#     create_supplier_profiles,
#     generate_supplier_email
# )
# from server.tools.web_search import google_search
# from server.tools.jina_reader import read_url
async def run_agent():
    mcp_url = "http://127.0.0.1:8000/sse"
    llm_client = get_client()
    print(f"🔌 Подключение к {mcp_url}...")

    try:
        async with sse_client(url=mcp_url) as streams:
            print("✅ Подключено к MCP-серверу!")

            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()

                # 1. Загрузка инструментов
                tools_list = await session.list_tools()
                openai_tools = []
                for tool in tools_list.tools:
                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.inputSchema
                        }
                    })
                print(f"🛠 Загружено инструментов: {len(openai_tools)}")

                # 2. System Prompt с инструкцией формата
                system_prompt = (
                    "Ты — профессиональный AI-менеджер по закупкам. Твоя цель: находить поставщиков, анализировать цены, проводить расчеты и вести переговоры.\n"
                    "Ты работаешь в цикле: Мысль -> Действие -> Наблюдение.\n\n"

                    "=== ТВОЙ ИНСТРУМЕНТАРИЙ ===\n"
                    "1. 🗄 ФАЙЛОВАЯ СИСТЕМА: Ты обязан вести досье на компании в папке `suppliers`.\n"
                    "2. 🧮 КАЛЬКУЛЯТОР: Используй инструмент `calculate` для любых вычислений.\n"
                    "3. 📧 ПОЧТА: Используй `send_supplier_email` для запроса прайс-листов.\n"
                    "4. 🌐 ПОИСК: `google_search`, `read_url`, `create_supplier_profiles`.\n"
                    "5. 📊 ОТЧЕТЫ: `create_suppliers_top_csv`.\n\n"

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

                    "ГЛАВНОЕ ПРАВИЛО: Твоя память ненадежна. Все важные данные (цены, контакты, история переписки) должны быть сохранены в файлы (.md) или таблицы (.csv)."
                )

                history = [{"role": "system", "content": system_prompt}]
                print("🤖 Агент готов! (введи 'exit')")

                while True:
                    user_input = await asyncio.to_thread(input, "\nВы: ")
                    if user_input.lower() in ["exit", "quit"]:
                        break

                    history.append({"role": "user", "content": user_input})

                    # --- ЦИКЛ АГЕНТА (ReAct Loop) ---
                    for step in range(25):
                        print(f"⏳ Шаг {step + 1}: Думаю...")

                        response = await llm_client.chat.completions.create(
                            # Платный люкс - Qwen/Qwen3-235B-A22B-Instruct-2507
                            # Дешевый калл - ai-sage/GigaChat3-10B-A1.8B
                            model="Qwen/Qwen3-235B-A22B-Instruct-2507",
                            messages=history,
                            tools=openai_tools if openai_tools else None,
                            tool_choice="auto" if openai_tools else None
                        )

                        response_message = response.choices[0].message
                        content = response_message.content or ""
                        tool_calls = response_message.tool_calls

                        custom_tool_call_data = None

                        # --- ПАРСЕР 1: ReAct (Action: ... Arguments: ...) ---
                        # Это то, что сейчас выдает ваша модель
                        action_match = re.search(r'Action:\s*([a-zA-Z0-9_]+)', content)
                        args_match = re.search(r'Arguments:\s*(\{.*?\})', content, re.DOTALL)

                        if action_match and args_match:
                            print("⚡ Распознан ReAct паттерн!")
                            try:
                                args_json = json.loads(args_match.group(1))
                                custom_tool_call_data = {
                                    "name": action_match.group(1).strip(),
                                    "arguments": args_json
                                }
                            except json.JSONDecodeError:
                                print("⚠️ Ошибка парсинга JSON аргументов в ReAct")

                        # --- ПАРСЕР 2: Сырой JSON (Резервный) ---
                        elif not tool_calls and "json" in content.lower() and "{" in content:
                            try:
                                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                                if json_match:
                                    potential_json = json.loads(json_match.group(0))
                                    if "name" in potential_json:
                                        custom_tool_call_data = potential_json
                                        print("⚡ Распознан JSON объект!")
                            except:
                                pass

                        # --- ЕСЛИ НЕТ ИНСТРУМЕНТОВ -> ВЫХОД ---
                        # Если мы ничего не распарсили и модель просто болтает
                        if not tool_calls and not custom_tool_call_data:
                            # Проверяем, не пытается ли она все же вызвать tool, но криво
                            if "Action:" in content:
                                # Если есть слово Action, но регулярка не сработала — пропускаем ход, пусть попробует еще раз (или выводим как есть)
                                pass

                            print(f"🤖 Ответ: {content}")
                            history.append(response_message)
                            break

                            # --- ПОДГОТОВКА К ВЫПОЛНЕНИЮ ---
                        history.append(response_message)

                        calls_to_execute = []
                        if tool_calls:
                            calls_to_execute = tool_calls
                        elif custom_tool_call_data:
                            class FakeToolCall:
                                def __init__(self, n, a):
                                    self.id = "call_custom"
                                    self.function = type('obj', (object,), {'name': n, 'arguments': json.dumps(a)})

                            calls_to_execute = [
                                FakeToolCall(custom_tool_call_data['name'], custom_tool_call_data['arguments'])]

                        # --- ИСПОЛНЕНИЕ ---
                        for tool_call in calls_to_execute:
                            function_name = tool_call.function.name
                            args_str = tool_call.function.arguments

                            if isinstance(args_str, str):
                                try:
                                    args_dict = json.loads(args_str)
                                except:
                                    args_dict = {}
                            else:
                                args_dict = args_str

                            print(f"🔄 Вызов: {function_name}({str(args_dict)[:100]}...)")

                            try:
                                result = await session.call_tool(function_name, arguments=args_dict)
                                tool_result = result.content[0].text
                                print(f"✅ Результат получен ({len(tool_result)} символов)")
                            except Exception as e:
                                tool_result = f"Error: {e}"
                                print(f"❌ Ошибка: {e}")

                            history.append({
                                "role": "tool",
                                "tool_call_id": getattr(tool_call, 'id', 'call_custom'),
                                "name": function_name,
                                "content": tool_result,
                            })

    except Exception as e:
        print("\n❌ КРИТИЧЕСКИЙ СБОЙ:")
        traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        print("\nРабота завершена.")