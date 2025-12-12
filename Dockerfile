# Используем легкий образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости (если нужны для сборки)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта
COPY . .

# Делаем скрипт запуска исполняемым
RUN chmod +x start.sh

# Открываем порт Streamlit (8501) и Сервера (8000)
EXPOSE 8501
EXPOSE 8000

# Запускаем скрипт
CMD ["./start.sh"]