@echo off
echo ========================================================
echo [MediCloak] Launching Browser with Proxy...
echo Proxy: http://localhost:8080
echo ========================================================

set "BROWSER_EXE="
if exist "C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe" (
    set "BROWSER_EXE=C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
) else if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
) else if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_EXE=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_EXE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
) else if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_EXE=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)

if defined BROWSER_EXE (
    start "" "%BROWSER_EXE%" --proxy-server="127.0.0.1:8080" --disable-quic --user-data-dir="%TEMP%\medicloak_browser" --ignore-certificate-errors https://chatgpt.com
) else (
    echo [!] No Chromium-based browser found at standard paths.
    pause
)

