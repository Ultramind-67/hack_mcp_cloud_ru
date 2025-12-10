# mcp_server/tools/export_tools.py
import csv
import os
import json
import re
from datetime import datetime
from mcp_server.mcp_instance import mcp
from mcp_server.utils import _require_env_vars


@mcp.tool(
    description="Экспортирует табличные данные в CSV файл. Args: data - строка с таблицей в Markdown или JSON, filename - имя файла (по умолчанию: export.csv)"
)
async def export_to_csv(data: str, filename: str = "export.csv") -> str:
    """
    Экспортирует табличные данные в CSV файл из Markdown таблицы или JSON.
    """
    try:
        # Создаем директорию для экспорта если не существует
        os.makedirs("exports", exist_ok=True)

        filepath = os.path.join("exports", filename)

        # Пытаемся определить формат данных
        if data.strip().startswith("|"):  # Markdown таблица
            csv_data = await _parse_markdown_table(data)
        elif data.strip().startswith("[") or data.strip().startswith("{"):  # JSON
            csv_data = await _parse_json_data(data)
        else:
            # Пытаемся найти таблицу в тексте
            table_match = re.search(r'(\|.*\|[\s\S]*?)(?=\n\n|\Z)', data)
            if table_match:
                csv_data = await _parse_markdown_table(table_match.group(1))
            else:
                return "❌ Не удалось распознать табличные данные. Убедитесь, что данные представлены в формате Markdown таблицы или JSON."

        if not csv_data:
            return "❌ Не удалось извлечь данные для экспорта."

        # Записываем в CSV
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(csv_data)

        return f"✅ Данные успешно экспортированы в: {filepath}\n📊 Строк: {len(csv_data) - 1}, Колонок: {len(csv_data[0])}"

    except Exception as e:
        return f"❌ Ошибка экспорта: {str(e)}"


async def _parse_markdown_table(markdown_table: str):
    """
    Парсит Markdown таблицу в список списков для CSV.
    """
    lines = [line.strip() for line in markdown_table.strip().split('\n') if line.strip()]

    # Убираем разделительные строки (| --- | --- |)
    filtered_lines = []
    for line in lines:
        if not re.match(r'^\|?[\s:---]+[\|:]', line) and '|' in line:
            filtered_lines.append(line)

    # Парсим строки с данными
    csv_data = []
    for line in filtered_lines:
        # Убираем начальный и конечный | если есть
        if line.startswith('|'):
            line = line[1:]
        if line.endswith('|'):
            line = line[:-1]

        # Разделяем по | и очищаем значения
        cells = [cell.strip() for cell in line.split('|')]
        csv_data.append(cells)

    return csv_data


async def _parse_json_data(json_str: str):
    """
    Парсит JSON данные в CSV формат.
    """
    try:
        data = json.loads(json_str)

        if isinstance(data, dict):
            # Один объект
            headers = list(data.keys())
            values = list(data.values())
            return [headers, values]
        elif isinstance(data, list) and data:
            # Массив объектов
            headers = list(data[0].keys())
            csv_data = [headers]
            for item in data:
                row = [str(item.get(h, '')) for h in headers]
                csv_data.append(row)
            return csv_data
        else:
            return None
    except json.JSONDecodeError:
        return None


@mcp.tool(
    description="Экспортирует результаты анализа поставщиков в CSV. Args: analysis_text - текст с анализом от LLM"
)
async def export_suppliers_analysis(analysis_text: str) -> str:
    """
    Специальная функция для экспорта анализа поставщиков из текста LLM.
    """
    try:
        # Ищем таблицу в тексте
        table_pattern = r'\|[^|\n]+\|[\s\S]*?(?=\n\n|\Z)'
        tables = re.findall(table_pattern, analysis_text)

        if not tables:
            return "❌ В тексте анализа не найдено табличных данных."

        # Берем первую найденную таблицу (обычно это основная)
        markdown_table = tables[0]

        # Генерируем имя файла с датой
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"suppliers_analysis_{timestamp}.csv"

        return await export_to_csv(markdown_table, filename)

    except Exception as e:
        return f"❌ Ошибка экспорта анализа: {str(e)}"


@mcp.tool(
    description="Создает CSV с топом поставщиков на основе таблицы из анализа"
)
async def create_suppliers_top_csv(analysis_text: str) -> str:
    """
    Создает CSV файл с топом поставщиков из текста анализа.
    """
    try:
        # Более специфичный паттерн для таблицы с поставщиками
        table_pattern = r'(\|.*Место.*Компания.*ИНН.*[\s\S]*?)(?=\n\n|\|?\s*\n\s*\n|\Z)'
        match = re.search(table_pattern, analysis_text, re.IGNORECASE)

        if not match:
            # Пробуем найти любую таблицу с цифрами и названиями компаний
            table_pattern2 = r'(\|\s*\d+\s*\|[^|]+\|\s*\d{10,}\s*\|[^|]+\|[^|]+\|[^|]+\|)'
            matches = re.findall(table_pattern2, analysis_text)
            if matches:
                # Собираем таблицу вручную
                headers = ["Место", "Компания", "ИНН", "Объём производства, тыс. руб.", "Динамика", "Регион"]
                rows = []
                for match in matches:
                    cells = [cell.strip() for cell in match.split('|') if cell.strip()]
                    if len(cells) >= 6:
                        rows.append(cells)

                if rows:
                    csv_data = [headers] + rows
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"top_suppliers_{timestamp}.csv"

                    filepath = os.path.join("exports", filename)
                    os.makedirs("exports", exist_ok=True)

                    with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerows(csv_data)

                    return f"✅ Топ поставщиков экспортирован в: {filepath}"

        if match:
            markdown_table = match.group(1)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"top_suppliers_{timestamp}.csv"
            return await export_to_csv(markdown_table, filename)

        return "❌ Не удалось найти таблицу с топом поставщиков в анализе."

    except Exception as e:
        return f"❌ Ошибка создания CSV: {str(e)}"