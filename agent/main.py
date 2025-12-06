import asyncio
import json
import traceback
import re
from mcp import ClientSession
from mcp.client.sse import sse_client
from llm_client import get_client
from dotenv import load_dotenv

load_dotenv()

# --- КЛЮЧИ ---

BASE_URL = "https://foundation-models.api.cloud.ru/v1"


async def run_agent():
    mcp_url = "http://127.0.0.1:8000/sse"
    llm_client = get_client()
    print(f"🔌 Подключение к {mcp_url}...")

    try:
        async with sse_client(url=mcp_url) as streams:
            print("✅ Подключено к MCP-серверу!")

            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()

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
                print("🤖 Агент готов! (введи 'exit')")

                # Добавляем системный промпт для стабильности
                history = [{
                    "role": "system",
                    "content": "Ты полезный бизнес-ассистент. Если нужно получить данные, используй доступные инструменты (functions). Не пиши технические теги в ответ."
                }]

                while True:
                    user_input = await asyncio.to_thread(input, "\nВы: ")
                    if user_input.lower() in ["exit", "quit"]:
                        break

                    history.append({"role": "user", "content": user_input})
                    print("⏳ Запрос к модели...")

                    response = await llm_client.chat.completions.create(
                        model="ai-sage/GigaChat3-10B-A1.8B",
                        messages=history,
                        tools=openai_tools if openai_tools else None,
                        tool_choice="auto" if openai_tools else None
                    )

                    response_message = response.choices[0].message
                    content = response_message.content or ""

                    # 1. Проверяем штатный tool_calls (если API работает идеально)
                    tool_calls = response_message.tool_calls

                    # 2. Проверяем "сырой" ответ GigaChat (наш случай)
                    # Ищем паттерн JSON внутри текста, если есть слова "function call" или просто JSON
                    custom_tool_call_data = None
                    if not tool_calls and "function call" in content:
                        try:
                            # Ищем JSON объект {...}
                            json_match = re.search(r'\{.*\}', content, re.DOTALL)
                            if json_match:
                                json_str = json_match.group(0)
                                custom_tool_call_data = json.loads(json_str)
                                print("⚡ Распознан сырой вызов функции из текста!")
                        except Exception as parse_err:
                            print(f"⚠️ Попытка парсинга сырого JSON не удалась: {parse_err}")

                    # --- ЛОГИКА ВЫПОЛНЕНИЯ ---

                    # Если сработал штатный механизм ИЛИ наш парсер
                    if tool_calls or custom_tool_call_data:

                        history.append(response_message)  # Сохраняем контекст

                        # Подготовка списка задач (либо одна из парсера, либо список из API)
                        calls_to_execute = []
                        if tool_calls:
                            calls_to_execute = tool_calls
                        elif custom_tool_call_data:
                            # Создаем псевдо-объект, чтобы код ниже был одинаковым
                            class FakeToolCall:
                                def __init__(self, name, args):
                                    self.id = "call_custom"
                                    self.function = type('obj', (object,),
                                                         {'name': name, 'arguments': json.dumps(args)})

                            calls_to_execute = [
                                FakeToolCall(custom_tool_call_data['name'], custom_tool_call_data['arguments'])]

                        for tool_call in calls_to_execute:
                            function_name = tool_call.function.name
                            args_str = tool_call.function.arguments

                            # Обработка аргументов
                            if isinstance(args_str, str):
                                try:
                                    args_dict = json.loads(args_str)
                                except:
                                    args_dict = {}
                            else:
                                args_dict = args_str  # Если уже словарь

                            print(f"🔄 MCP Запрос: {function_name}({args_dict})")

                            try:
                                result = await session.call_tool(function_name, arguments=args_dict)
                                tool_result = result.content[0].text
                                print(f"✅ MCP Ответ: {tool_result}")
                            except Exception as mcp_err:
                                tool_result = f"Error: {str(mcp_err)}"
                                print(f"❌ Ошибка MCP: {mcp_err}")

                            # Добавляем результат в историю
                            history.append({
                                "role": "tool",
                                "tool_call_id": getattr(tool_call, 'id', 'call_custom'),
                                "name": function_name,
                                "content": tool_result,
                            })

                        # Финальный ответ модели
                        print("⏳ Генерирую итог...")
                        final_response = await llm_client.chat.completions.create(
                            model="ai-sage/GigaChat3-10B-A1.8B",
                            messages=history
                        )
                        final_text = final_response.choices[0].message.content

                        # Очистка от мусора, если модель снова выдаст теги
                        final_text = final_text.replace("<|message_sep|>", "").strip()
                        print(f"🤖 Ответ: {final_text}")
                        history.append(final_response.choices[0].message)

                    else:
                        # Обычный ответ
                        print(f"🤖 Ответ: {content}")
                        history.append(response_message)

    except Exception as e:
        print("\n❌ КРИТИЧЕСКИЙ СБОЙ:")
        traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        print("\nРабота завершена.")