import os
import importlib
import pkgutil
from mcp_server.mcp_instance import mcp
import mcp_server.tools as tools_package
from dotenv import load_dotenv

load_dotenv()

def register_all_tools():
    """Автоматически импортирует все модули из папки tools"""
    package_path = tools_package.__path__
    for _, name, _ in pkgutil.iter_modules(package_path):
        importlib.import_module(f"mcp_server.tools.{name}")
        print(f"📦 Загружен модуль инструментов: {name}")

def main():
    register_all_tools()

    # Настройки как мы обсуждали
    mcp.run(transport="sse", host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()