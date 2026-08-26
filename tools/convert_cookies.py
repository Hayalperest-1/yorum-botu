"""
Google oturumu kaydetme - 2. YÖNTEM (save_google_session.py çalışmadıysa,
yani Google "bu tarayıcı/uygulama güvenli olmayabilir" diyip otomatik
tarayıcıdan girişi ENGELLEDİYSE bunu kullan).

Bu script, senin NORMAL (otomasyon olmayan, her gün kullandığın) Chrome'unda
zaten açık olan Google oturumunun çerezlerini bir tarayıcı uzantısıyla dışa
aktardıktan sonra, bunları Playwright'ın anlayacağı formata çevirir.

ADIM ADIM:
  1) Chrome Web Mağazası'ndan "Cookie-Editor" uzantısını kur (ücretsiz,
     cgagnier tarafından yapılan, çok kullanılan bir uzantı).
  2) NORMAL Chrome'unda (Google hesabına zaten giriş yapmış olduğun
     tarayıcı) şu adrese git: https://www.google.com/maps
  3) Sağ üstteki Cookie-Editor uzantı ikonuna tıkla.
  4) Açılan pencerede "Export" (dışa aktar) butonuna tıkla - bu, o
     sayfanın çerezlerini JSON olarak PANOYA (clipboard) kopyalar.
  5) Bir Not Defteri (Notepad) aç, Ctrl+V ile yapıştır, şu isimle bu
     "tools" klasörüne kaydet: cookies_export.json
  6) Bu scripti çalıştır (elindeki .venv'i aktive ettikten sonra):
       python tools\\convert_cookies.py
  7) Oluşan "tools/google_session.json" dosyasının İÇERİĞİNİN TAMAMINI
     kopyalayıp GitHub'da GOOGLE_STORAGE_STATE secret'ına yapıştır
     (repo -> Settings -> Secrets and variables -> Actions).

Bu dosyaları (cookies_export.json / google_session.json) ASLA GitHub'a
normal dosya olarak commit'leme - ikisi de neredeyse şifre kadar hassas
(ikisi de .gitignore'a eklendi, ama yine de dikkatli ol).
"""

import json
import os
import sys

TOOLS_DIR = os.path.dirname(__file__)
INPUT_PATH = os.path.join(TOOLS_DIR, "cookies_export.json")
OUTPUT_PATH = os.path.join(TOOLS_DIR, "google_session.json")

# Playwright sadece bu üç değeri kabul ediyor; tarayıcı uzantılarının
# kullandığı isimlerden çeviriyoruz.
SAME_SITE_MAP = {
    "no_restriction": "None",
    "unspecified": "Lax",
    "lax": "Lax",
    "strict": "Strict",
    "none": "None",
}


def _convert_one(raw: dict) -> dict:
    name = raw.get("name")
    value = raw.get("value")
    domain = raw.get("domain", "")
    path = raw.get("path", "/")

    # Farklı uzantılar farklı alan isimleri kullanıyor - hepsini deniyoruz.
    expires = raw.get("expirationDate")
    if expires is None:
        expires = raw.get("expires")
    if expires is None:
        expires = raw.get("expiry")
    if expires is None or raw.get("session") is True:
        expires = -1  # Playwright'ta "oturum çerezi" (tarayıcı kapanınca silinir) demek

    same_site_raw = str(raw.get("sameSite", "unspecified")).lower()
    same_site = SAME_SITE_MAP.get(same_site_raw, "Lax")

    return {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "expires": expires,
        "httpOnly": bool(raw.get("httpOnly", False)),
        "secure": bool(raw.get("secure", True)),
        "sameSite": same_site,
    }


def main():
    if not os.path.exists(INPUT_PATH):
        print(f"HATA: '{INPUT_PATH}' bulunamadı.")
        print("Önce bu dosyanın üstündeki açıklamadaki adımları takip et "
              "(Cookie-Editor uzantısıyla dışa aktarıp bu isimle kaydet).")
        sys.exit(1)

    with open(INPUT_PATH, encoding="utf-8") as f:
        raw_cookies = json.load(f)

    if not isinstance(raw_cookies, list):
        print("HATA: Beklenmeyen format - dosyanın içeriği bir liste ([...]) olmalı.")
        sys.exit(1)

    # Sadece google.com ile ilgili çerezleri alıyoruz (Cookie-Editor zaten
    # sadece o sekmenin sayfasının çerezlerini dışa aktarır ama yine de
    # bir güvenlik/temizlik önlemi olarak filtreliyoruz).
    google_cookies = [c for c in raw_cookies if "google.com" in c.get("domain", "")]

    if not google_cookies:
        print("UYARI: 'google.com' içeren hiç çerez bulunamadı - dışa aktarımı "
              "www.google.com/maps sayfasındayken yaptığından emin misin?")

    converted = [_convert_one(c) for c in google_cookies]

    state = {"cookies": converted, "origins": []}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f)

    print(f"Kaydedildi: {OUTPUT_PATH} ({len(converted)} çerez)")
    print()
    print("ŞİMDİ ŞUNU YAP:")
    print(f"  1) '{OUTPUT_PATH}' dosyasını bir metin editörüyle aç, İÇERİĞİNİN TAMAMINI kopyala")
    print("  2) GitHub'da repo -> Settings -> Secrets and variables -> Actions")
    print("  3) 'New repository secret' -> İsim: GOOGLE_STORAGE_STATE -> Değer: kopyaladığın JSON")
    print("  4) Kaydet")


if __name__ == "__main__":
    main()
