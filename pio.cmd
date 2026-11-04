@echo off
setlocal
set "PLATFORMIO_CORE_DIR=%~dp0.platformio"
"%~dp0.venv\Scripts\python.exe" -m platformio %*
exit /b %errorlevel%
