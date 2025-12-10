# Используем Python 3.11 (как у вас в venv)
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта в контейнер
COPY . .

# Открываем порт 8000 (на нем работает сервер)
EXPOSE 8000

# Команда запуска сервера
CMD ["python", "-m", "mcp_server.server"]