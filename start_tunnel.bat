@echo off
chcp 65001 >nul
cls
color 0A
echo.
echo ================================================================
echo           TTS READER - PUBLIC ACCESS TUNNEL
echo ================================================================
echo.
echo IMPORTANT: Make sure start.bat is running in another window!
echo.
echo Starting SSH tunnel...
echo.
echo ================================================================
echo.

ssh -o StrictHostKeyChecking=no -R 80:localhost:5000 nokey@localhost.run

echo.
echo ================================================================
echo Tunnel closed. Press any key to exit.
echo ================================================================
pause >nul
