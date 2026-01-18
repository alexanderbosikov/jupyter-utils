#!/usr/bin/env bash

set -euo pipefail

echo "=== Установка базовых зависимостей ==="

if command -v apt &> /dev/null; then
    sudo apt update -y
    sudo apt install -y python3 python3-venv python3-pip git curl
fi

echo "=== Установка Poetry (если ещё нет) ==="
if ! command -v poetry &> /dev/null; then
    curl -sSL https://install.python-poetry.org | python3 -
    
    # Добавляем в PATH (один раз)
    export PATH="$HOME/.local/bin:$PATH"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    source ~/.bashrc
fi

echo "=== Клонируем / обновляем репозиторий ==="
if [ ! -d ".git" ]; then
    git clone https://github.com/curiosity888/jupyter-utils.git .
else
    git pull origin main
fi

echo "=== Установка зависимостей ==="
poetry install --no-root   # или --no-root если не хочешь editable

# Опционально: editable install, если хочешь редактировать код
# poetry install

echo "=== Запуск Jupyter Lab ==="
poetry run jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root &

echo ""
echo "Готово! Jupyter запущен."
echo "Открой в браузере: http://localhost:8888 (или IP сервера:8888)"
echo "Токен: poetry run jupyter server list | grep token"