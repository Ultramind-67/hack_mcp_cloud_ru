# app.py
import streamlit as st
import asyncio
import os
import pandas as pd
from agent.core import AgentClient

# --- CONFIG ---
st.set_page_config(
    page_title="Procurement AI",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS ---
st.markdown("""
<style>
    /* Основной фон и шрифт */
    .stApp {
        background-color: #f8f9fa;
    }

    /* Блоки чата */
    .stChatMessage {
        background-color: white;
        border: 1px solid #e0e0e0;
        border-radius: 15px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        padding: 10px;
    }

    /* Сайдбар */
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e0e0e0;
    }

    /* Заголовки */
    h1, h2, h3 {
        color: #2c3e50;
    }

    /* Метрики */
    [data-testid="stMetricValue"] {
        font-size: 1.5rem;
        color: #2e86de;
    }
</style>
""", unsafe_allow_html=True)

# --- INIT STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []  # История чата
    # Приветственное сообщение
    st.session_state.messages.append({
        "role": "assistant",
        "content": "Здравствуйте! Я ваш AI-ассистент по закупкам. \n\nЯ умею искать поставщиков, анализировать их сайты и формировать сводные таблицы. \n\n**Какую задачу решим сегодня?**"
    })

if "agent" not in st.session_state:
    st.session_state.agent = AgentClient()


# --- HELPERS ---
def count_files(directory, ext):
    if not os.path.exists(directory): return 0
    return len([f for f in os.listdir(directory) if f.endswith(ext)])


def load_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "Ошибка чтения файла"


# --- SIDEBAR (DASHBOARD) ---
with st.sidebar:
    st.title("Панель управления")

    # Метрики
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Досье", count_files("suppliers", ".md"))
    with col2:
        st.metric("Отчеты", count_files("exports", ".csv"))

    st.divider()

    # Вкладки
    tab_profiles, tab_reports = st.tabs(["📂 Досье компаний", "📊 CSV Отчеты"])

    # Вкладка 1: Профили
    with tab_profiles:
        if os.path.exists("suppliers"):
            files = sorted([f for f in os.listdir("suppliers") if f.endswith(".md")])
            if files:
                selected_profile = st.selectbox("Выберите компанию", files, label_visibility="collapsed")
                if selected_profile:
                    content = load_file(os.path.join("suppliers", selected_profile))
                    st.info(f"Файл: {selected_profile}")
                    st.markdown(content, unsafe_allow_html=True)
            else:
                st.caption("Нет данных. Попросите агента найти поставщиков.")
        else:
            st.caption("Папка пуста.")

    # Вкладка 2: Таблицы
    with tab_reports:
        if os.path.exists("exports"):
            csvs = sorted([f for f in os.listdir("exports") if f.endswith(".csv")], reverse=True)
            if csvs:
                selected_csv = st.selectbox("Выберите отчет", csvs, label_visibility="collapsed")
                if selected_csv:
                    file_path = os.path.join("exports", selected_csv)
                    try:
                        df = pd.read_csv(file_path)
                        st.dataframe(df, hide_index=True, use_container_width=True)

                        with open(file_path, "rb") as f:
                            st.download_button(
                                "⬇️ Скачать Excel/CSV",
                                data=f,
                                file_name=selected_csv,
                                mime="text/csv",
                                use_container_width=True
                            )
                    except:
                        st.error("Неверный формат CSV")
            else:
                st.caption("Нет отчетов.")

    st.divider()
    if st.button("🗑 Сброс диалога", use_container_width=True):
        st.session_state.messages = []
        st.session_state.agent = AgentClient()  # Сброс памяти агента
        st.rerun()

# --- MAIN CHAT AREA ---
st.header("🏢 Корпоративный поиск и аналитика")

# Отрисовка истории
for msg in st.session_state.messages:
    avatar = "👤" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# Поле ввода
if prompt := st.chat_input("Например: Найди поставщиков серверного оборудования в Москве"):

    # 1. Показываем сообщение пользователя
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # 2. Ответ агента
    with st.chat_message("assistant", avatar="🤖"):
        status_box = st.status("🚀 Запускаю процесс закупки...", expanded=True)


        def update_status(text):
            status_box.write(text)


        try:
            # Запуск асинхронной логики
            response_text = asyncio.run(
                st.session_state.agent.process_message(prompt, update_status)
            )

            status_box.update(label="✅ Анализ завершен", state="complete", expanded=False)
            st.markdown(response_text)

            # Сохраняем ответ
            st.session_state.messages.append({"role": "assistant", "content": response_text})

            # Принудительно обновляем страницу, чтобы в сайдбаре появились новые файлы
            st.rerun()

        except Exception as e:
            status_box.update(label="❌ Ошибка", state="error")
            st.error(f"Произошла ошибка: {e}")