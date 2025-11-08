@echo off
chcp 65001 >nul
echo ================================================
echo TTS Reader - Установка зависимостей
echo ================================================
echo.

cd /d "%~dp0"

echo [INFO] Проверка Python 3.11...
set PYTHON311=C:\Python311\python.exe
if not exist "%PYTHON311%" (
    echo [ERROR] Python 3.11 не найден в C:\Python311\
    echo [INFO] Установите Python 3.11 или измените путь в батнике
    pause
    exit /b 1
)

echo [INFO] Проверка виртуального окружения...
if not exist "venv\" (
    echo [INFO] Создание виртуального окружения с Python 3.11...
    "%PYTHON311%" -m venv venv
    if errorlevel 1 (
        echo [ERROR] Не удалось создать виртуальное окружение
        pause
        exit /b 1
    )
    echo [SUCCESS] Виртуальное окружение создано
)

echo.
echo [INFO] Установка базовых библиотек...
venv\Scripts\pip.exe install Flask flask-cors

echo.
echo [INFO] Установка библиотек для обработки аудио...
venv\Scripts\pip.exe install librosa soundfile numpy scipy pydub

echo.
echo [INFO] Установка PyTorch 2.5 (CPU версия - совместимая с TTS)...
venv\Scripts\pip.exe install "torch<2.6" "torchaudio<2.6" --index-url https://download.pytorch.org/whl/cpu

echo.
echo [INFO] Установка TTS (XTTS v2)...
venv\Scripts\pip.exe install TTS

echo.
echo [INFO] Установка совместимой версии transformers...
venv\Scripts\pip.exe install "transformers<4.42"

echo.
echo ================================================
echo Установка завершена!
echo ================================================
echo.
echo Следующие шаги:
echo 1. Запустите convert_audio.bat для конвертации MP3 в WAV
echo 2. Запустите start.bat для запуска приложения
echo.

pause
