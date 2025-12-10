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
    .stApp { background-color: #f8f9fa; }
    .stChatMessage {
        background-color: white;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 15px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    /* Блокируем сайдбар визуально, если идет загрузка (опционально) */
    div[data-testid="stSidebar"] {
        transition: opacity 0.3s;
    }
</style>
""", unsafe_allow_html=True)

# --- STATE INIT ---
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": "Здравствуйте! Я готов искать поставщиков и анализировать цены. \n\n**Введите запрос ниже.**"
    }]

if "agent" not in st.session_state:
    st.session_state.agent = AgentClient()

if "processing" not in st.session_state:
    st.session_state.processing = False


# --- HELPERS ---
def count_files(directory, ext):
    if not os.path.exists(directory): return 0
    return len([f for f in os.listdir(directory) if f.endswith(ext)])


def load_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "Ошибка чтения"


# --- SIDEBAR ---
with st.sidebar:
    st.title("📦 Управление")

    # Метрики
    c1, c2 = st.columns(2)
    c1.metric("Досье", count_files("suppliers", ".md"))
    c2.metric("Отчеты", count_files("exports", ".csv"))

    st.divider()

    # Вкладки (disabled во время генерации, чтобы не сбить процесс)
    tab1, tab2 = st.tabs(["📂 Досье", "📊 CSV"])

    with tab1:
        if os.path.exists("suppliers"):
            files = sorted([f for f in os.listdir("suppliers") if f.endswith(".md")])
            if files:
                # ВАЖНО: key="sb_files" чтобы состояние не терялось
                selected = st.selectbox(
                    "Выберите компанию",
                    files,
                    label_visibility="collapsed",
                    key="sb_files",
                    disabled=st.session_state.processing
                )
                if selected:
                    st.info(f"📄 {selected}")
                    st.markdown(load_file(os.path.join("suppliers", selected)), unsafe_allow_html=True)
            else:
                st.caption("Нет данных")
        else:
            st.caption("Папка пуста")

    with tab2:
        if os.path.exists("exports"):
            csvs = sorted([f for f in os.listdir("exports") if f.endswith(".csv")], reverse=True)
            if csvs:
                # ВАЖНО: key="sb_csv"
                sel_csv = st.selectbox(
                    "Выберите отчет",
                    csvs,
                    label_visibility="collapsed",
                    key="sb_csv",
                    disabled=st.session_state.processing
                )
                if sel_csv:
                    fp = os.path.join("exports", sel_csv)
                    try:
                        df = pd.read_csv(fp)
                        st.dataframe(df, hide_index=True)
                        with open(fp, "rb") as f:
                            st.download_button(
                                "⬇️ Скачать",
                                f,
                                file_name=sel_csv,
                                mime="text/csv",
                                disabled=st.session_state.processing
                            )
                    except:
                        st.error("Ошибка CSV")
            else:
                st.caption("Нет отчетов")

    st.divider()
    if st.button("🗑 Очистить историю", key="btn_reset", disabled=st.session_state.processing, use_container_width=True):
        st.session_state.messages = []
        st.session_state.agent = AgentClient()  # Сброс памяти агента
        st.rerun()

# --- CHAT AREA ---
st.header("🏢 AI Закупщик")

# Рендер истории
for msg in st.session_state.messages:
    avatar = "👤" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# Поле ввода (блокируется если идет обработка, хотя streamlit сам это делает, но для надежности)
if prompt := st.chat_input("Например: Найди поставщиков фанеры в СПб", disabled=st.session_state.processing):

    # 1. Устанавливаем флаг "В работе"
    st.session_state.processing = True

    # 2. Добавляем сообщение юзера и сразу перерисовываем, чтобы заблокировать сайдбар
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # 3. Блок ответа
    with st.chat_message("assistant", avatar="🤖"):
        status = st.status("🚀 Запуск агента...", expanded=True)

        try:
            # Запуск логики
            response = asyncio.run(st.session_state.agent.process_message(prompt, status.write))

            # Если ответ пустой
            if not response or not response.strip():
                response = "✅ Данные собраны и сохранены в файлы. (Текстовый ответ отсутствует)"

            status.update(label="Готово!", state="complete", expanded=False)
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

        except Exception as e:
            status.update(label="Ошибка", state="error")
            st.error(f"Сбой: {e}")

        finally:
            # 4. Снимаем флаг "В работе" и обновляем интерфейс
            st.session_state.processing = False
            st.rerun()