@echo off
REM ============================================================
REM  Google Yorum -> Instagram Hikaye Botu - Yerel test baslatici
REM
REM  Cift tikla, yeterli:
REM   1) Sanal ortam (.venv) yoksa olusturur
REM   2) requirements.txt'deki TUM kutuphaneleri kurar/gunceller
REM      (ileride requirements.txt'ye yeni bir kutuphane eklenirse
REM      bu script degismeden otomatik onu da kurar)
REM   3) .env dosyasi varsa oradaki ayarlari okuyup botu calistirir
REM
REM  NOT: Botun asil calistigi yer GitHub Actions (bulut) - bu script
REM  sadece kendi bilgisayarinda deneme/test yapman icin.
REM ============================================================

setlocal
cd /d "%~dp0"

echo.
echo === Google Yorum -^> Instagram Hikaye Botu ===
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo HATA: Python bulunamadi.
    echo https://www.python.org/downloads/ adresinden Python kur.
    echo Kurulum ekraninda "Add python.exe to PATH" kutucugunu isaretlemeyi UNUTMA.
    echo.
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

echo [2/3] Kutuphaneler kontrol ediliyor / kuruluyor...
python -m pip install --upgrade pip >nul 2>nul
pip install -r requirements.txt
if errorlevel 1 (
    echo HATA: Kutuphaneler kurulamadi, yukaridaki hataya bak.
    pause
    exit /b 1
)

if not exist ".env" (
    echo.
    echo UYARI: ".env" dosyasi bulunamadi.
    echo ".env.example" dosyasini ".env" olarak kopyalayip
    echo icindeki degerleri doldurman gerekiyor, yoksa bot
    echo eksik ayar hatasi verecek.
    echo.
)

echo [3/3] Bot calistiriliyor...
echo.
python -m automation.main

echo.
echo Bitti. Bu pencereyi kapatabilirsin.
pause
