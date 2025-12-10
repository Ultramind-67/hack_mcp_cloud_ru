import os
import importlib
import pkgutil
import sys
from mcp_server.mcp_instance import mcp
import mcp_server.tools as tools_package
from dotenv import load_dotenv

load_dotenv()


def register_all_tools():
    """Автоматически импортирует все модули из папки tools с отладкой"""
    print("📂 Сканирую папку tools...")
    package_path = tools_package.__path__
    count = 0
    for _, name, _ in pkgutil.iter_modules(package_path):
        try:
            importlib.import_module(f"mcp_server.tools.{name}")
            print(f"   ✅ Загружен модуль: {name}")
            count += 1
        except Exception as e:
            print(f"   ❌ Ошибка загрузки {name}: {e}")

    if count == 0:
        print("⚠️ ВНИМАНИЕ: Инструменты не найдены! Проверьте папку mcp_server/tools/")


def main():
    # Добавляем текущую директорию в путь, чтобы импорты работали корректно
    sys.path.append(os.getcwd())

    register_all_tools()

    print("\n🚀 ЗАПУСК СЕРВЕРА...")
    print(f"🔗 Адрес: http://127.0.0.1:8000/sse")
    print("⏳ Ожидание подключений (не закрывайте это окно!)...")

    # ВАЖНО: host="127.0.0.1" (не localhost, не 0.0.0.0) для Mac OS
    mcp.run(transport="sse", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()