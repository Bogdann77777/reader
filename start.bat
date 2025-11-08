@echo off
chcp 65001 >nul
echo ================================================
echo TTS Reader - Запуск приложения
echo ================================================
echo.

cd /d "%~dp0"

echo [INFO] Проверка виртуального окружения...
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Виртуальное окружение не найдено
    echo [INFO] Сначала запустите install.bat
    pause
    exit /b 1
)

echo [INFO] Проверка версии Python...
for /f "tokens=2 delims= " %%i in ('venv\Scripts\python.exe --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [INFO] Используется Python %PYTHON_VERSION%

echo [INFO] Запуск Flask сервера...
echo [INFO] Приложение будет доступно по адресу: http://localhost:5000
echo.
echo ================================================
echo Для остановки нажмите Ctrl+C
echo ================================================
echo.

venv\Scripts\python.exe app.py

pause
