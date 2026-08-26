@echo off
REM ============================================================
REM  Google oturumu kaydetme araci - TEK SEFERLIK kurulum
REM
REM  Cift tikla, yeterli:
REM   1) Sanal ortam (.venv) yoksa olusturur (baslat.bat ile aynisi)
REM   2) Kutuphaneleri kurar, Playwright'in Chrome'unu indirir
REM   3) tools/save_google_session.py'yi calistirir - bir tarayici
REM      penceresi acilacak, orada Google hesabinla giris yapacaksin
REM
REM  Sonucunda "tools/google_session.json" olusuyor - icerigini
REM  GitHub'da "GOOGLE_STORAGE_STATE" secret'i olarak eklemen gerekiyor
REM  (script sonunda tam talimat yaziyor).
REM ============================================================

setlocal
cd /d "%~dp0"

echo.
echo === Google oturumu kaydetme araci ===
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo HATA: Python bulunamadi.
    echo https://www.python.org/downloads/ adresinden Python kur.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [1/3] Sanal ortam olusturuluyor...
    python -m venv .venv
) else (
    echo [1/3] Sanal ortam zaten var, atlaniyor.
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo HATA: Sanal ortam etkinlestirilemedi.
    pause
    exit /b 1
)

echo [2/3] Kutuphaneler ve Chrome kontrol ediliyor / kuruluyor (ilk seferde biraz surebilir)...
python -m pip install --upgrade pip >nul 2>nul
pip install -r requirements.txt
if errorlevel 1 (
    echo HATA: Kutuphaneler kurulamadi, yukaridaki hataya bak.
    pause
    exit /b 1
)
playwright install chromium
if errorlevel 1 (
    echo HATA: Chrome indirilemedi, yukaridaki hataya bak.
    pause
    exit /b 1
)

echo [3/3] Oturum kaydetme araci baslatiliyor...
echo.
python tools\save_google_session.py

echo.
echo Bitti. Bu pencereyi kapatabilirsin.
pause
