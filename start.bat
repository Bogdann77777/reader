@echo off
cls

echo.
echo ================================================================
echo           TTS READER - STARTING SERVER
echo ================================================================
echo.

cd /d "%~dp0"

:: Kill old processes
echo [1/4] Cleaning old processes...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM ngrok.exe >nul 2>&1
timeout /t 2 /nobreak >nul

:: Get IP
echo [2/4] Getting IP address...
set LOCAL_IP=127.0.0.1
for /f "tokens=14" %%a in ('ipconfig ^| findstr "192.168"') do set LOCAL_IP=%%a
if "%LOCAL_IP%"=="127.0.0.1" for /f "tokens=14" %%a in ('ipconfig ^| findstr "10."') do set LOCAL_IP=%%a

:: Check venv
echo [3/4] Checking environment...
if not exist "venv\Scripts\python.exe" (
    echo.
    echo ERROR: Virtual environment not found!
    echo Please run install.bat first
    echo.
    pause
    exit /b
)

:: Start server
echo [4/4] Starting server...
start "TTS Server" cmd /k "venv\Scripts\python.exe app.py"

:: Wait for server
echo.
echo Waiting for server to start (45 seconds)...
timeout /t 45 /nobreak >nul

:: Check port
netstat -an 2>nul | findstr :9000 >nul
if errorlevel 1 (
    echo.
    echo ERROR: Server did not start!
    echo Check the server window for details.
    pause
    exit /b
)

echo Server started!
echo.

:: Start ngrok
echo Starting ngrok tunnel...
start "ngrok" /min ngrok http 9000
timeout /t 8 /nobreak >nul

:: Get ngrok URL
echo Getting public URL...
timeout /t 2 /nobreak >nul

curl -s http://127.0.0.1:4040/api/tunnels 2>nul | findstr "https://" | findstr "public_url" > ngrok_temp.txt
set NGROK_URL=
for /f "tokens=*" %%a in (ngrok_temp.txt) do (
    set LINE=%%a
)
del ngrok_temp.txt 2>nul

if defined LINE (
    for /f "tokens=2 delims=:" %%a in ("%LINE%") do set PART1=%%a
    for /f "tokens=3 delims=:" %%a in ("%LINE%") do set PART2=%%a
    set PART1=%PART1:"=%
    set PART1=%PART1: =%
    set PART1=%PART1:,=%
    set PART2=%PART2:"=%
    set PART2=%PART2: =%
    set PART2=%PART2:,=%
    set NGROK_URL=https:%PART1%:%PART2%
)

:: Show all links
cls
echo.
echo ================================================================
echo                 READY! YOUR LINKS:
echo ================================================================
echo.
echo 1. LOCAL ACCESS (this computer only):
echo    http://localhost:9000
echo.
echo 2. LOCAL NETWORK (WiFi/home devices):
echo    http://%LOCAL_IP%:9000
echo.
echo 3. PUBLIC ACCESS (anywhere in the world):
if defined NGROK_URL (
    echo    %NGROK_URL%
    echo %NGROK_URL% | clip
    echo.
    echo    Link copied to clipboard!
) else (
    echo    Open: http://127.0.0.1:4040
    echo    to see your ngrok URL
)
echo.
echo ================================================================
echo    DO NOT CLOSE THIS WINDOW!
echo ================================================================
echo.
pause >nul

:: Stop everything
taskkill /F /IM ngrok.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
echo Stopped!
timeout /t 2 >nul
