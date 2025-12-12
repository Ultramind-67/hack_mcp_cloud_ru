#!/bin/bash

# 1. Запускаем MCP сервер в фоновом режиме (& в конце)
echo "🚀 Запускаю MCP Сервер..."
python -m mcp_server.server &

# Ждем пару секунд, чтобы сервер успел подняться
sleep 5

# 2. Запускаем Streamlit на переднем плане
echo "🎨 Запускаю Интерфейс..."
streamlit run app.py --server.port=8501 --server.address=0.0.0.0