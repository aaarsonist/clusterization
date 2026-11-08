@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Сегментация клиентов: запуск

echo ============================================================
echo   Программное средство сегментации клиентов: запуск
echo ============================================================

docker info >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Docker Desktop не запущен. Запустите Docker Desktop и повторите попытку.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\init-env.ps1"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось создать файл параметров .env.
    pause
    exit /b 1
)
if not exist backups mkdir backups

echo [1/2] Сборка и запуск контейнеров (первый запуск занимает несколько минут)...
docker compose up -d --build --wait
if errorlevel 1 (
    echo [ОШИБКА] Не удалось запустить контейнеры. Журнал: docker compose logs
    pause
    exit /b 1
)

echo [2/2] Заполнение базы демонстрационными данными (только при первом запуске)...
docker compose exec -T backend_core python scripts/seed_data.py --if-empty

echo.
echo ============================================================
echo   Система запущена:  https://localhost:8443
echo   Маркетолог:        marketer / Marketer#2026
echo   Администратор:     admin / Admin#2026
echo   Остановка:         stop.bat
echo ============================================================
start "" https://localhost:8443
pause
