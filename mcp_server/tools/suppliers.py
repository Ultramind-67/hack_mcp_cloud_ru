import os
import re
import json
import datetime
from mcp_server.mcp_instance import mcp

# Создаем директории
os.makedirs("suppliers", exist_ok=True)
os.makedirs("suppliers/raw_responses", exist_ok=True)

@mcp.tool(
    description="Поиск поставщиков по запросу. Args: query - товар/услуга + регион, pages - кол-во страниц (макс 3)."
)
async def find_suppliers(query: str, pages: int = 1) -> str:
    """Ищет поставщиков через Google Search и возвращает структурированные данные"""
    try:
        from .web_search import perform_google_search
    except ImportError:
        return "❌ Ошибка: инструмент 'web_search' не найден. Убедитесь, что файл web_search.py существует в папке tools."

    all_results = []

    for page in range(pages):
        start = page * 10 + 1
        # Получаем текстовый результат от вашего инструмента
        search_text = await perform_google_search(
            query=f"{query} поставщик контакты телефон email сайт отзывы",
            start=start,
            num_results=10
        )

        # Парсим текстовый формат вашего инструмента
        items = re.findall(
            r'\d+\.\s*\[([^\]]+)\]\((https?://[^\s\)]+)\)\s*\n\s*([^\n]+)',
            search_text,
            re.IGNORECASE | re.DOTALL
        )

        for title, url, snippet in items:
            # Фильтрация нерелевантных доменов
            bad_domains = ["wikipedia", "youtube", "hh.ru", "avito", "2gis", "google", "maps", "yandex"]
            if any(bad in url.lower() for bad in bad_domains):
                continue

            # Извлекаем домен для имени файла
            domain_match = re.search(r'https?://(?:www\.)?([^/]+)', url)
            domain = domain_match.group(1).lower() if domain_match else re.sub(r'[^\w\-]', '_', query)[:20]

            all_results.append({
                "title": title.strip(),
                "url": url.strip(),
                "snippet": snippet.strip()[:200],  # Обрезаем длинные сниппеты
                "domain": domain,
                "search_query": query
            })

    if not all_results:
        return "Не найдено подходящих поставщиков. Попробуйте изменить запрос или добавить регион."

    return json.dumps(all_results, ensure_ascii=False, indent=2)

@mcp.tool(
    description="Генерирует профиль поставщика с разделами для LLM-контекста. Args: raw_data - JSON с url и контентом сайта"
)
async def generate_supplier_profile(raw_data: str) -> str:
    """Создаёт Markdown-профиль со специальными разделами для сохранения контекста LLM"""
    try:
        data = json.loads(raw_data)
        url = data.get("url", "")
        content = data.get("content", "")
        domain = data.get("domain", "unknown_supplier")

        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        # Шаблон профиля с разделами для контекста LLM
        template = f"""
# ООО "[Название компании]"

## Основное
- **Название:** ООО "[Укажите название из контента]"
- **Контакты:** [телефоны; email]
- **Сайт:** {url}
- **ИНН:** [найди в тексте или "Нет данных"]

## Продукция
- **Основной товар:** [основной продукт из контента]
- **Цены:** [конкретные цифры или "по запросу"]
- **Мин. заказ:** [объем/вес]
- **Сроки:** [дни производства + доставки]

## Локация
- **Город:** [город из URL или текста]
- **Адрес:** [полный юридический адрес]

## Оценки AI (1-10)
- **Цена:** [оценка за конкурентоспособность]
- **Качество:** [оценка по описанию продукции]
- **Скорость:** [оценка по срокам]
- **Репутация:** [оценка по отзывам и истории]
- **Общий рейтинг:** [среднее из предыдущих]

## Логистика
- **Доставка:** [условия доставки]
- **Регионы:** [регионы поставок]

## Условия
- **Оплата:** [методы оплаты]
- **Гарантия:** [срок гарантии]
- **НДС:** [да/нет/уточняется]

## История
- **Заказов:** [примерное количество или "Нет данных"]
- **Средний чек:** [примерная сумма]
- **Последний заказ:** [дата или "Нет данных"]

## Запросы в LLM
- **{current_time}**
  [Сгенерирован запрос для поставщика:
  "Здравствуйте! Мы заинтересованы в вашей продукции. Пожалуйста, предоставьте информацию по:
  • Ценам за единицу/объем
  • Минимальному объему заказа
  • Срокам поставки
  • Условиям оплаты и доставки
  С уважением, [Ваша компания]"]

## Полученные сообщения от LLM
- **{current_time}**
  [Пока нет ответа от поставщика. После получения ответа сюда будет добавлен текст письма и анализ LLM]

---
<!-- META: DO_NOT_MODIFY_STRUCTURE -->
<!-- RAW_DATA_SOURCE: {url} -->
<!-- PROFILE_CREATED: {current_time} -->
<!-- LLM_CONTEXT_STORE: ACTIVE -->
"""
        return template.strip()
    except json.JSONDecodeError:
        return f"❌ Ошибка: Неверный формат JSON в raw_data. Получено: {raw_data[:100]}..."
    except Exception as e:
        return f"❌ Ошибка генерации профиля: {str(e)}"

@mcp.tool(
    description="Сохраняет профиль в .md файл с защитой от перезаписи существующих данных"
)
async def save_supplier_profile(content: str, domain: str) -> str:
    """Сохраняет или обновляет профиль поставщика с сохранением истории LLM-взаимодействий"""
    try:
        # Нормализуем имя файла
        safe_domain = re.sub(r'[\\/*?:"<>|]', "", domain).replace(" ", "_").lower()
        filename = f"{safe_domain}.md"
        filepath = os.path.join("suppliers", filename)

        # Если файл существует - сливаем данные
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                existing_content = f.read()

            # Извлекаем существующие разделы LLM-контекста
            llm_queries_match = re.search(r'(## Запросы в LLM.*?)(?=## |\Z)', existing_content, re.DOTALL)
            llm_responses_match = re.search(r'(## Полученные сообщения от LLM.*?)(?=## |\Z)', existing_content, re.DOTALL)

            if llm_queries_match and llm_responses_match:
                # Сохраняем существующие разделы
                llm_queries = llm_queries_match.group(1).strip()
                llm_responses = llm_responses_match.group(1).strip()

                # Заменяем разделы в новом контенте
                new_content = re.sub(
                    r'## Запросы в LLM.*?## Полученные сообщения от LLM.*?(?=## |\Z)',
                    f'{llm_queries}\n\n{llm_responses}',
                    content,
                    flags=re.DOTALL
                )
                content = new_content

        # Сохраняем файл
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content.strip())

        return f"✅ Профиль сохранён/обновлён: {filepath}"
    except Exception as e:
        return f"❌ Ошибка сохранения: {str(e)}"

@mcp.tool(
    description="Добавляет запись в историю LLM-взаимодействий поставщика"
)
async def add_llm_interaction(domain: str, query: str = "", response: str = "") -> str:
    """
    Добавляет запись в разделы 'Запросы в LLM' или 'Полученные сообщения от LLM'
    """
    try:
        safe_domain = re.sub(r'[\\/*?:"<>|]', "", domain).replace(" ", "_").lower()
        filepath = os.path.join("suppliers", f"{safe_domain}.md")

        if not os.path.exists(filepath):
            return f"❌ Файл профиля не найден: {filepath}. Сначала создайте профиль."

        # Читаем текущее содержимое
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        new_entry = ""

        # Определяем тип записи
        if query:
            section_header = "## Запросы в LLM"
            new_entry = f"- **{current_time}**  \n  {query.strip()}\n"
        elif response:
            section_header = "## Полученные сообщения от LLM"
            new_entry = f"- **{current_time}**  \n  {response.strip()}\n"
        else:
            return "❌ Укажите query или response для добавления записи."

        # Находим раздел и добавляем запись
        if section_header in content:
            # Добавляем запись в конец раздела
            pattern = re.compile(rf'({section_header}.*?)(\n## |\Z)', re.DOTALL)
            def add_entry(match):
                section_content = match.group(1)
                return section_content + "\n" + new_entry + match.group(2)

            updated_content = pattern.sub(add_entry, content)

            # Сохраняем обновленный файл
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(updated_content)

            return f"✅ Запись добавлена в раздел '{section_header}' для {domain}"
        else:
            return f"❌ Раздел '{section_header}' не найден в файле профиля."

    except Exception as e:
        return f"❌ Ошибка обновления: {str(e)}"

@mcp.tool(
    description="Полный цикл: поиск → парсинг → генерация → сохранение профилей"
)
async def create_supplier_profiles(query: str) -> str:
    """Автоматизирует создание профилей первых 3 поставщиков из поиска"""
    try:
        from .jina_reader import read_url
    except ImportError:
        return "❌ Ошибка: инструмент 'jina_reader' не найден. Убедитесь, что файл jina_reader.py существует в папке tools."

    # 1. Ищем поставщиков
    search_results = await find_suppliers(query, pages=1)
    if "Не найдено" in search_results or "Ошибка" in search_results:
        return search_results

    try:
        suppliers = json.loads(search_results)
    except json.JSONDecodeError:
        return f"❌ Ошибка парсинга результатов поиска: {search_results[:200]}..."

    results = []

    # 2. Обрабатываем максимум 3 поставщика
    for i, supplier in enumerate(suppliers[:3], 1):
        url = supplier["url"]
        domain = supplier["domain"]

        # 3. Читаем контент сайта
        content = await read_url(url)
        if "Ошибка" in content or "не удалось" in content.lower():
            results.append(f"⚠️ {domain}: Не удалось прочитать сайт ({content[:100]}...)")
            continue

        # 4. Готовим данные для генерации
        raw_data = json.dumps({
            "url": url,
            "content": content,
            "domain": domain
        }, ensure_ascii=False)

        # 5. Генерируем профиль
        profile_template = await generate_supplier_profile(raw_data)
        if profile_template.startswith("❌"):
            results.append(f"⚠️ {domain}: {profile_template}")
            continue

        # 6. Сохраняем профиль
        save_result = await save_supplier_profile(profile_template, domain)
        results.append(save_result)

    return "\n".join(results)

