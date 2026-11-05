@echo off
setlocal
pushd "%~dp0"
"%~dp0.venv\Scripts\python.exe" -X utf8 -m server.admin %*
set "admin_exit=%errorlevel%"
pause
popd
exit /b %admin_exit%
