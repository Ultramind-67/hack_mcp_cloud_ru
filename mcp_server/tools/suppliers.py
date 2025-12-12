import os
import re
import json
import datetime
from mcp_server.mcp_instance import mcp

# Импортируем инструменты RAG для интеграции памяти
# Используем try-except на случай, если файл rag_tools еще не создан или есть ошибки импорта
try:
    from mcp_server.tools import rag_tools

    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("⚠️ RAG tools не найдены. Работаем без памяти.")

# Создаем директории
os.makedirs("suppliers", exist_ok=True)
os.makedirs("suppliers/raw_responses", exist_ok=True)


# ==========================================
# ВНУТРЕННЯЯ ЛОГИКА (Обычные функции)
# ==========================================

async def _find_suppliers_logic(query: str, pages: int = 1) -> str:
    """Внутренняя логика поиска поставщиков (только Web)"""
    try:
        from .web_search import perform_google_search
    except ImportError:
        return "❌ Ошибка: инструмент 'web_search' не найден."

    all_results = []

    for page in range(pages):
        start = page * 10 + 1
        search_text = await perform_google_search(
            query=f"{query} поставщик контакты телефон email сайт отзывы",
            start=start,
            num_results=10
        )

        items = re.findall(
            r'\d+\.\s*\[([^\]]+)\]\((https?://[^\s\)]+)\)\s*\n\s*([^\n]+)',
            search_text,
            re.IGNORECASE | re.DOTALL
        )

        for title, url, snippet in items:
            bad_domains = ["wikipedia", "youtube", "hh.ru", "avito", "2gis", "google", "maps", "yandex", "dzen"]
            if any(bad in url.lower() for bad in bad_domains):
                continue

            domain_match = re.search(r'https?://(?:www\.)?([^/]+)', url)
            domain = domain_match.group(1).lower() if domain_match else re.sub(r'[^\w\-]', '_', query)[:20]

            all_results.append({
                "title": title.strip(),
                "url": url.strip(),
                "snippet": snippet.strip()[:200],
                "domain": domain,
                "search_query": query
            })

    if not all_results:
        return "Не найдено новых поставщиков в Google."

    return json.dumps(all_results, ensure_ascii=False, indent=2)


async def _generate_supplier_profile_logic(raw_data: str) -> str:
    """Внутренняя логика генерации профиля"""
    try:
        data = json.loads(raw_data)
        url = data.get("url", "")
        domain = data.get("domain", "unknown_supplier")
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

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
        return f"❌ Ошибка: Неверный формат JSON в raw_data."
    except Exception as e:
        return f"❌ Ошибка генерации профиля: {str(e)}"


async def _save_supplier_profile_logic(content: str, domain: str) -> str:
    """Внутренняя логика сохранения профиля + АВТО-ИНДЕКСАЦИЯ В RAG"""
    try:
        safe_domain = re.sub(r'[\\/*?:"<>|]', "", domain).replace(" ", "_").lower()
        filename = f"{safe_domain}.md"
        filepath = os.path.join("suppliers", filename)

        # Логика слияния (сохраняем историю LLM)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                existing_content = f.read()

            llm_queries_match = re.search(r'(## Запросы в LLM.*?)(?=## |\Z)', existing_content, re.DOTALL)
            llm_responses_match = re.search(r'(## Полученные сообщения от LLM.*?)(?=## |\Z)', existing_content,
                                            re.DOTALL)

            if llm_queries_match and llm_responses_match:
                llm_queries = llm_queries_match.group(1).strip()
                llm_responses = llm_responses_match.group(1).strip()

                new_content = re.sub(
                    r'## Запросы в LLM.*?## Полученные сообщения от LLM.*?(?=## |\Z)',
                    f'{llm_queries}\n\n{llm_responses}',
                    content,
                    flags=re.DOTALL
                )
                content = new_content

        # 1. Сохраняем на диск
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content.strip())

        msg = f"✅ Профиль сохранён/обновлён: {filepath}"

        # 2. АВТОМАТИЧЕСКАЯ ИНДЕКСАЦИЯ (RAG)
        if RAG_AVAILABLE:
            try:
                print(f"🧠 Начинаю авто-индексацию файла: {filepath}")
                # ВАЖНО: Вызываем _logic функцию, а не tool wrapper!
                # Убедитесь, что в rag_tools.py есть функция _index_document_logic
                index_result = await rag_tools._index_document_logic(filepath)

                if "✅" in index_result:
                    msg += "\n🧠 Досье успешно добавлено в базу знаний (RAG)."
                else:
                    msg += f"\n⚠️ RAG ошибка: {index_result}"
            except AttributeError:
                msg += "\n⚠️ Ошибка: в rag_tools нет функции _index_document_logic. Обновите rag_tools.py."
            except Exception as e:
                msg += f"\n⚠️ Сбой индексации: {e}"

        return msg
    except Exception as e:
        return f"❌ Ошибка сохранения: {str(e)}"


# ==========================================
# MCP ИНСТРУМЕНТЫ
# ==========================================

@mcp.tool(
    description="УМНЫЙ ПОИСК поставщиков. 1. Проверяет локальную базу знаний (RAG). 2. Если там пусто — ищет в Google. Args: query, pages."
)
async def find_suppliers(query: str, pages: int = 1) -> str:
    """
    Гибридный поиск: Local Memory -> Web Search.
    Позволяет избегать повторного гугления, если поставщик уже найден ранее.
    """
    output_parts = []

    # 1. Сначала проверяем RAG (Локальную память)
    if RAG_AVAILABLE:
        print(f"🧠 Проверяю базу знаний по запросу: {query}...")
        try:
            # ВАЖНО: Вызываем _logic функцию!
            rag_result = await rag_tools._search_knowledge_base_logic(query)

            if "Ничего не найдено" not in rag_result and "В базе знаний ничего" not in rag_result:
                output_parts.append(f"📂 **НАЙДЕНО В ЛОКАЛЬНОЙ БАЗЕ (Собранные досье):**\n{rag_result}")
                output_parts.append("\n---\n")
            else:
                print("🧠 В базе знаний пусто по этому запросу.")
        except AttributeError:
            print("⚠️ Ошибка: в rag_tools нет функции _search_knowledge_base_logic.")
        except Exception as e:
            print(f"⚠️ Ошибка RAG при поиске: {e}")

    # 2. Идем в Google
    print(f"🌐 Иду в Google по запросу: {query}...")
    web_result = await _find_suppliers_logic(query, pages)

    if web_result.strip().startswith("["):
        output_parts.append(f"🌍 **РЕЗУЛЬТАТЫ ИЗ ИНТЕРНЕТА (Google):**\n{web_result}")
    else:
        output_parts.append(f"🌍 **РЕЗУЛЬТАТЫ WEB:** {web_result}")

    return "\n".join(output_parts)


@mcp.tool(
    description="Генерирует профиль поставщика с разделами для LLM-контекста. Args: raw_data - JSON с url и контентом сайта"
)
async def generate_supplier_profile(raw_data: str) -> str:
    return await _generate_supplier_profile_logic(raw_data)


@mcp.tool(
    description="Сохраняет профиль в .md файл И АВТОМАТИЧЕСКИ ИНДЕКСИРУЕТ его в базу знаний."
)
async def save_supplier_profile(content: str, domain: str) -> str:
    return await _save_supplier_profile_logic(content, domain)


@mcp.tool(
    description="Добавляет запись в историю LLM-взаимодействий поставщика"
)
async def add_llm_interaction(domain: str, query: str = "", response: str = "") -> str:
    try:
        safe_domain = re.sub(r'[\\/*?:"<>|]', "", domain).replace(" ", "_").lower()
        filepath = os.path.join("suppliers", f"{safe_domain}.md")

        if not os.path.exists(filepath):
            return f"❌ Файл профиля не найден: {filepath}. Сначала создайте профиль."

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        new_entry = ""

        if query:
            section_header = "## Запросы в LLM"
            new_entry = f"- **{current_time}**  \n  {query.strip()}\n"
        elif response:
            section_header = "## Полученные сообщения от LLM"
            new_entry = f"- **{current_time}**  \n  {response.strip()}\n"
        else:
            return "❌ Укажите query или response."

        if section_header in content:
            pattern = re.compile(rf'({section_header}.*?)(\n## |\Z)', re.DOTALL)

            def add_entry(match):
                return match.group(1) + "\n" + new_entry + match.group(2)

            updated_content = pattern.sub(add_entry, content)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(updated_content)

            return f"✅ Запись добавлена в '{section_header}' для {domain}"
        else:
            return f"❌ Раздел '{section_header}' не найден."

    except Exception as e:
        return f"❌ Ошибка обновления: {str(e)}"


@mcp.tool(
    description="Полный цикл: поиск → парсинг → генерация → сохранение профилей (С АВТО-ИНДЕКСАЦИЕЙ)"
)
async def create_supplier_profiles(query: str) -> str:
    """Автоматизирует создание профилей первых 3 поставщиков из поиска"""
    try:
        from .jina_reader import read_url
    except ImportError:
        return "❌ Ошибка: инструмент 'jina_reader' не найден."

    # 1. Ищем поставщиков (Только веб, так как мы создаем новые профили)
    search_results = await _find_suppliers_logic(query, pages=1)

    if "Не найдено" in search_results or "Ошибка" in search_results:
        return search_results

    try:
        suppliers = json.loads(search_results)
    except json.JSONDecodeError:
        return f"❌ Ошибка парсинга поиска: {search_results[:200]}..."

    results = []

    # 2. Обрабатываем максимум 3 поставщика
    for i, supplier in enumerate(suppliers[:3], 1):
        url = supplier["url"]
        domain = supplier["domain"]

        content = await read_url(url)
        if "Ошибка" in content or "не удалось" in content.lower():
            results.append(f"⚠️ {domain}: Не удалось прочитать сайт")
            continue

        raw_data = json.dumps({
            "url": url,
            "content": content,
            "domain": domain
        }, ensure_ascii=False)

        profile_template = await _generate_supplier_profile_logic(raw_data)

        if profile_template.startswith("❌"):
            results.append(f"⚠️ {domain}: {profile_template}")
            continue

        # ВЫЗЫВАЕМ ЛОГИКУ СОХРАНЕНИЯ (ОНА ЖЕ И ИНДЕКСИРУЕТ В RAG)
        save_result = await _save_supplier_profile_logic(profile_template, domain)
        results.append(save_result)

    return "\n".join(results)