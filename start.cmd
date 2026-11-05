@echo off
setlocal
pushd "%~dp0"
"%~dp0.venv\Scripts\python.exe" -m server %*
set "server_exit=%errorlevel%"
popd
exit /b %server_exit%
