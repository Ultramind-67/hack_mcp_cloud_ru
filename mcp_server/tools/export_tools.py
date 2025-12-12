import csv
import os
import json
import re
import requests
from datetime import datetime
from mcp_server.mcp_instance import mcp

# --- НАСТРОЙКИ ЯНДЕКСА ---
YANDEX_TOKEN = os.getenv("YANDEX_DISK_TOKEN")


def _upload_to_yandex_disk(local_path: str, remote_filename: str) -> str:
    """
    Вспомогательная функция для загрузки файла на Яндекс.Диск.
    Возвращает публичную ссылку или None, если произошла ошибка.
    """
    if not YANDEX_TOKEN or "ВСТАВЬ" in YANDEX_TOKEN:
        print("⚠️ Яндекс Токен не настроен.")
        return None

    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}

    try:
        # 1. Получаем URL для загрузки
        upload_url_resp = requests.get(
            'https://cloud-api.yandex.net/v1/disk/resources/upload',
            headers=headers,
            params={'path': remote_filename, 'overwrite': 'true'},
            timeout=10
        )

        if upload_url_resp.status_code != 200:
            print(f"Ошибка получения URL загрузки: {upload_url_resp.json()}")
            return None

        href = upload_url_resp.json()['href']

        # 2. Загружаем файл
        with open(local_path, 'rb') as f:
            upload_resp = requests.put(href, files={'file': f}, timeout=30)

        if upload_resp.status_code != 201:
            print(f"Ошибка загрузки файла: {upload_resp.status_code}")
            return None

        # 3. Публикуем файл (делаем доступным по ссылке)
        requests.put(
            'https://cloud-api.yandex.net/v1/disk/resources/publish',
            headers=headers,
            params={'path': remote_filename},
            timeout=10
        )

        # 4. Получаем публичную ссылку
        meta_resp = requests.get(
            'https://cloud-api.yandex.net/v1/disk/resources',
            headers=headers,
            params={'path': remote_filename},
            timeout=10
        )

        info = meta_resp.json()
        return info.get('public_url')

    except Exception as e:
        print(f"⚠️ Исключение при работе с Яндекс.Диском: {e}")
        return None


@mcp.tool(
    description="Экспортирует табличные данные в CSV файл и загружает на Яндекс.Диск."
)
async def export_to_csv(data: str, filename: str = "export.csv") -> str:
    try:
        os.makedirs("exports", exist_ok=True)
        filepath = os.path.join("exports", filename)

        csv_data = await _parse_any_data(data)
        if not csv_data:
            return "❌ Данные не распознаны."

        # 1. Сохраняем локально
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(csv_data)

        response_msg = f"✅ Экспорт успешен (локально): {filepath}"

        # 2. Загружаем в облако
        public_link = _upload_to_yandex_disk(filepath, filename)

        if public_link:
            response_msg += f"\n☁️ Ссылка на Яндекс.Диск: {public_link}"
        else:
            response_msg += "\n⚠️ Не удалось загрузить на Яндекс.Диск (см. логи), но локальный файл сохранен."

        return response_msg

    except Exception as e:
        return f"Ошибка: {e}"


@mcp.tool(
    description="Создает CSV с топом поставщиков из текста, сохраняет локально и на Яндекс.Диск."
)
async def create_suppliers_top_csv(analysis_text: str) -> str:
    """
    Универсальный парсер таблиц для отчетов с выгрузкой в облако.
    """
    try:
        os.makedirs("exports", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"top_suppliers_{timestamp}.csv"
        filepath = os.path.join("exports", filename)

        # 1. Пытаемся найти Markdown таблицу
        rows = re.findall(r'^\s*\|.*\|.*$', analysis_text, re.MULTILINE)

        if not rows:
            return "❌ В тексте не найдено строк таблицы (формат Markdown)."

        # 2. Парсим строки
        csv_data = []
        for row in rows:
            if '---' in row:
                continue
            cells = [cell.strip() for cell in row.strip().split('|')]
            # Чистка пустых краев
            if len(cells) > 2 and cells[0] == '' and cells[-1] == '':
                cells = cells[1:-1]
            elif len(cells) > 1 and cells[0] == '':
                cells = cells[1:]
            elif len(cells) > 1 and cells[-1] == '':
                cells = cells[:-1]

            if any(cells):
                csv_data.append(cells)

        if not csv_data:
            return "❌ Таблица найдена, но не удалось извлечь данные."

        # 3. Сохраняем локально
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(csv_data)

        response_msg = f"✅ Таблица сохранена локально: {filepath}\n📊 Строк: {len(csv_data)}"

        # 4. Загружаем в облако
        # Используем то же имя файла, что и локально
        public_link = _upload_to_yandex_disk(filepath, filename)

        if public_link:
            response_msg += f"\n☁️ **Ссылка для скачивания:** {public_link}"
        else:
            response_msg += "\n⚠️ Ошибка выгрузки в Яндекс.Диск (токен неверен или сбой сети)."

        return response_msg

    except Exception as e:
        return f"❌ Критическая ошибка: {str(e)}"


async def _parse_any_data(data):
    if data.strip().startswith("[") or data.strip().startswith("{"):
        try:
            return json.loads(data)
        except:
            pass
    return None