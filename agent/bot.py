import asyncio
import json
import traceback
import re
import os
import sys

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

from dotenv import load_dotenv

# Импорты MCP
from mcp import ClientSession
from mcp.client.sse import sse_client

try:
    from .llm_client import get_client
except ImportError:
    from llm_client import get_client

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    print("❌ Ошибка: Не найден TELEGRAM_TOKEN в .env")
    sys.exit(1)

bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

USER_HISTORIES = {}
mcp_session: ClientSession = None
openai_tools = []

# --- SYSTEM PROMPT ---
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

    "ГЛАВНОЕ ПРАВИЛО: Если речь о конкретной компании-поставщике, результат должен лежать в .md\n\n"

    "ВАЖНОЕ ПРАВИЛО ФОРМАТИРОВАНИЯ:\n"
    "Отвечай в Telegram используя Markdown. Жирный шрифт для важного, списки для перечисления."
)


def get_user_history(user_id: int):
    if user_id not in USER_HISTORIES:
        USER_HISTORIES[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return USER_HISTORIES[user_id]


def clean_content(text: str) -> str:
    """Очистка ответа от мусора, но сохранение смысла."""
    if not text: return ""
    # Убираем только спецтокены GigaChat
    text = text.replace("<|message_sep|>", "").replace("<|role_sep|>", "")
    return text.strip()


@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    user_id = message.from_user.id
    USER_HISTORIES[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    await message.answer(
        "👋 **Привет! Я твой AI-агент по закупкам.**\n\n"
        "Я умею:\n"
        "🔍 Искать поставщиков (`create_supplier_profiles`)\n"
        "📂 Вести досье в файлах\n"
        "📊 Экспортировать данные в CSV\n\n"
        "Напиши задачу, например:\n"
        "_«Найди поставщиков офисной мебели в Москве и составь таблицу»_"
    )


@dp.message(Command("clear"))
async def command_clear_handler(message: types.Message):
    user_id = message.from_user.id
    USER_HISTORIES[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    await message.answer("🧹 Контекст очищен.")


@dp.message(F.text)
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    history = get_user_history(user_id)
    history.append({"role": "user", "content": message.text})

    status_msg = await message.answer("⏳ _Анализирую задачу..._")
    llm_client = get_client()

    try:
        final_answer = ""
        # ReAct Loop
        for step in range(25):
            await bot.send_chat_action(chat_id=message.chat.id, action="typing")

            response = await llm_client.chat.completions.create(
                model="Qwen/Qwen3-235B-A22B-Instruct-2507",
                messages=history,
                tools=openai_tools if openai_tools else None,
                tool_choice="auto" if openai_tools else None
            )

            response_message = response.choices[0].message
            content = clean_content(response_message.content or "")
            tool_calls = response_message.tool_calls
            custom_tool_call_data = None

            # --- ПАРСЕР 1: ReAct (Action: ... Arguments: ...) ---
            action_match = re.search(r'Action:\s*([a-zA-Z0-9_]+)', content)
            args_match = re.search(r'Arguments:\s*(\{.*?\})', content, re.DOTALL)

            if action_match and args_match:
                try:
                    args_json = json.loads(args_match.group(1))
                    custom_tool_call_data = {"name": action_match.group(1).strip(), "arguments": args_json}
                except:
                    pass

            # --- ПАРСЕР 2: XML <tool_call> (СПЕЦИАЛЬНО ДЛЯ QWEN) ---
            # Вот этот блок мы добавили
            elif not tool_calls:
                xml_match = re.search(r'<tool_call>(.*?)</tool_call>', content, re.DOTALL)
                if xml_match:
                    try:
                        custom_tool_call_data = json.loads(xml_match.group(1))
                        # Если модель написала мысли перед тегом, мы их видим в логах, но не шлем юзеру как ответ
                        print(f"💭 Мысли модели: {content.replace(xml_match.group(0), '').strip()}")
                    except:
                        pass

            # --- ПАРСЕР 3: Сырой JSON ---
            if not tool_calls and not custom_tool_call_data and "json" in content.lower() and "{" in content:
                try:
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        potential_json = json.loads(json_match.group(0))
                        if "name" in potential_json:
                            custom_tool_call_data = potential_json
                except:
                    pass

            # === ЛОГИКА ВЫХОДА ===
            # Если инструментов нет - это ответ пользователю
            if not tool_calls and not custom_tool_call_data:
                final_answer = content
                history.append(response_message)
                break

                # Если инструмент НАЙДЕН -> Выполняем его, а текст считаем "мыслями" и не шлем пользователю
            history.append(response_message)

            calls_to_execute = []
            if tool_calls:
                calls_to_execute = tool_calls
            elif custom_tool_call_data:
                class FakeToolCall:
                    def __init__(self, n, a):
                        self.id = "call_custom"
                        self.function = type('obj', (object,), {'name': n, 'arguments': json.dumps(a)})

                calls_to_execute = [FakeToolCall(custom_tool_call_data['name'], custom_tool_call_data['arguments'])]

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

                # Обновляем статус
                try:
                    await status_msg.edit_text(f"🔄 _Выполняю: {function_name}..._")
                except:
                    pass

                # Вызов MCP
                try:
                    result = await mcp_session.call_tool(function_name, arguments=args_dict)
                    tool_result = result.content[0].text
                except Exception as e:
                    tool_result = f"Error: {e}"

                history.append({
                    "role": "tool",
                    "tool_call_id": getattr(tool_call, 'id', 'call_custom'),
                    "name": function_name,
                    "content": tool_result,
                })

        # Финал
        try:
            await status_msg.delete()
        except:
            pass

        if final_answer:
            try:
                await message.answer(final_answer, parse_mode=ParseMode.MARKDOWN)
            except TelegramBadRequest:
                # Fallback если Markdown сломан
                await message.answer(final_answer, parse_mode=None)
        else:
            await message.answer("⚠️ Я выполнил действия, но не сформировал текстовый ответ.")

    except Exception as e:
        traceback.print_exc()
        await message.answer(f"❌ Ошибка: {e}")


async def main():
    mcp_url = "http://127.0.0.1:8000/sse"
    print(f"🔌 Connecting to {mcp_url}...")
    async with sse_client(url=mcp_url) as streams:
        print("✅ MCP Connected!")
        async with ClientSession(streams[0], streams[1]) as session:
            global mcp_session, openai_tools
            mcp_session = session
            await session.initialize()

            tools_list = await session.list_tools()
            openai_tools = [{"type": "function",
                             "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema}}
                            for t in tools_list.tools]
            print(f"🛠 Tools: {len(openai_tools)}")

            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")