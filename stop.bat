@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Остановка программного средства сегментации клиентов...
docker compose down
echo [OK] Контейнеры остановлены. Данные сохранены в томе postgres_data, резервные копии - в папке backups.
pause
