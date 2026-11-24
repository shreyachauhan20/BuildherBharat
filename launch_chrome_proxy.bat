@echo off
title MediCloak Proxied Chrome Launcher
color 0a

echo ========================================================
echo   [MediCloak] Launching Proxied Chrome...
echo   Proxy: http://127.0.0.1:8080
echo   Target: https://chatgpt.com
echo ========================================================

set "CHROME_EXE="
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_EXE=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    set "CHROME_EXE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)

if defined CHROME_EXE (
    echo Opening Chrome with proxy and QUIC disabled...
    start "" "%CHROME_EXE%" --proxy-server="127.0.0.1:8080" --disable-quic --user-data-dir="%TEMP%\medicloak_chrome" --ignore-certificate-errors https://chatgpt.com
) else (
    echo [ERROR] Chrome not found.
    pause
)
