@echo off
REM ============================================================
REM  Cerez donusturme araci (Google oturumu icin 2. yontem)
REM
REM  Once tools/convert_cookies.py dosyasinin ustundeki adimlari
REM  takip edip "tools/cookies_export.json" dosyasini olusturmus
REM  olman gerekiyor. Sonra bu dosyaya cift tikla.
REM ============================================================

setlocal
cd /d "%~dp0"

echo.
echo === Cerez donusturme araci ===
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo HATA: Python bulunamadi.
    echo https://www.python.org/downloads/ adresinden Python kur.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Sanal ortam olusturuluyor...
    python -m venv .venv
)

call ".venv\Scripts\activate.bat"

python tools\convert_cookies.py

echo.
pause
