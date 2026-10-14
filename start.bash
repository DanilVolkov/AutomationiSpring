#!/usr/bin/env bash

echo "========================================"
echo "           Запуск приложения"
echo "========================================"
echo ""

# ---------- Проверка Python ----------
if ! command -v python3 >/dev/null 2>&1; then
    echo "[ОШИБКА] Python не найден в PATH."
    echo "Установите Python 3.14+ с https://www.python.org/downloads/"
    read -rp "Нажмите Enter для выхода..."
    exit 1
fi

# ---------- Проверка uv ----------
if ! command -v uv >/dev/null 2>&1; then
    echo "[ОШИБКА] uv не найден."
    echo "Установите uv:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "После установки перезапустите терминал."
    read -rp "Нажмите Enter для выхода..."
    exit 1
fi

# ---------- Синхронизация зависимостей ----------
echo "[1/4] Синхронизация зависимостей..."
if ! uv sync; then
    echo "[ОШИБКА] Синхронизация не прошла."
    echo "Проверьте pyproject.toml / uv.lock."
    read -rp "Нажмите Enter для выхода..."
    exit 1
fi

# ---------- Проверка .env ----------
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "[2/4] Файл .env не найден. Копирую из .env.example..."
        cp .env.example .env
        echo ""
        echo "[ВАЖНО] Заполните .env перед запуском!"
        echo ""
        read -rp "Нажмите Enter для выхода..."
        exit 1
    fi
else
    echo "[2/4] Файл .env найден"
fi

# ---------- Миграции ----------
echo "[3/4] Применение миграций..."
cd ./ispring/ || {
    echo "[ОШИБКА] Не удалось перейти в директорию ./ispring/"
    read -rp "Нажмите Enter для выхода..."
    exit 1
}

if ! uv run python manage.py migrate; then
    echo "[ОШИБКА] Миграции не применились."
    read -rp "Нажмите Enter для выхода..."
    exit 1
fi

# ---------- Сервер ----------
echo "[4/4] Запуск сервера..."
echo ""
echo "========================================"
echo "   Откройте сайт: http://127.0.0.1:8000/"
echo "========================================"
echo ""

uv run python manage.py runserver