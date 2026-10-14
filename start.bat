@echo off
chcp 65001 >nul
setlocal

echo ========================================
echo           Запуск приложения
echo ========================================
echo.

REM ---------- Проверка Python ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Python не найден в PATH.
    echo Установите Python 3.14+ с https://www.python.org/downloads/
    pause
    exit /b 1
)

REM ---------- Проверка uv ----------
where uv >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] uv не найден.
    echo Установите uv:
    echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    echo После установки перезапустите терминал ^(cmd/PowerShell^).
    pause
    exit /b 1
)

REM ---------- Синхронизация зависимостей ----------
echo [1/4] Синхронизация зависимостей...
uv sync
if errorlevel 1 (
    echo [ОШИБКА] Синхронизация не прошла.
    echo Проверьте pyproject.toml / uv.lock.
    pause
    exit /b 1
)

REM ---------- Проверка .env ----------
if not exist ".env" (
    if exist ".env.example" (
        echo [2/4] Файл .env не найден. Копирую из .env.example...
        copy .env.example .env >nul
        echo.
        echo [ВАЖНО] Заполните .env перед запуском!
        echo.
        pause
	exit /b 1
    )
) else (
    echo [2/4] Файл .env найден
)

REM ---------- Миграции ----------
echo [3/4] Применение миграций...
cd .\ispring\
uv run python manage.py migrate
if errorlevel 1 (
    echo [ОШИБКА] Миграции не применились.
    pause
    exit /b 1
)

REM ---------- Сервер ----------
echo [4/4] Запуск сервера...
echo.
echo ========================================
echo   Откройте сайт: http://127.0.0.1:8000/
echo ========================================
echo.

uv run python manage.py runserver

endlocal
pause