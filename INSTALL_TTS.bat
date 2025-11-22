@echo off
cls
echo ================================================================
echo           INSTALLING XTTS DEPENDENCIES
echo ================================================================
echo.

cd /d "%~dp0"

echo [1/3] Upgrading pip...
venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
echo.

echo [2/3] Installing TTS (Coqui-TTS)...
echo This may take 5-10 minutes...
venv\Scripts\python.exe -m pip install TTS
echo.

echo [3/3] Installing other requirements...
venv\Scripts\python.exe -m pip install -r requirements.txt
echo.

echo ================================================================
echo           TESTING INSTALLATION
echo ================================================================
echo.

venv\Scripts\python.exe -c "from TTS.api import TTS; print('✅ TTS installed successfully!')"
if errorlevel 1 (
    echo.
    echo ❌ TTS installation FAILED!
    echo.
    pause
    exit /b 1
)

venv\Scripts\python.exe -c "import flask; print('✅ Flask OK')"
venv\Scripts\python.exe -c "import torch; print('✅ PyTorch OK')"
venv\Scripts\python.exe -c "import soundfile; print('✅ soundfile OK')"

echo.
echo ================================================================
echo           INSTALLATION COMPLETE!
echo ================================================================
echo.
echo You can now run: start.bat
echo.
pause
