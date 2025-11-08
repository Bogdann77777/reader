@echo off
chcp 65001 >nul
echo ================================================
echo TTS Reader - Конвертация MP3 в WAV
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

echo [INFO] Запуск конвертации...
echo.

venv\Scripts\python.exe convert_audio.py

echo.
echo ================================================
echo Конвертация завершена!
echo ================================================
echo.

pause
