"""
Tüm ayarlar ortam değişkenlerinden (environment variables) okunur.
GitHub Actions üzerinde bunlar "Repository secrets" olarak saklanır -
kod içine asla gerçek anahtar/şifre yazma.

Her değişkenin ne olduğu ve nereden alınacağı README.md içinde anlatılıyor.
"""

import os


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(
            f"Eksik ortam değişkeni: {name}. "
            f"Yerelde test ediyorsan bunu '.env' dosyana ekle; botu buluta (GitHub Actions) "
            f"aldığında ise repo Settings > Secrets and variables > Actions kısmına ekleyeceksin."
        )
    return val


class Config:
    # --- Gmail (yeni yorumları buradan yakalıyoruz - Google Business
    # Profile API'sinin kısıtlı/onaylı erişimine gerek yok) ---
    GMAIL_ADDRESS = _require("GMAIL_ADDRESS")
    GMAIL_APP_PASSWORD = _require("GMAIL_APP_PASSWORD")

    # Bu Gmail hesabı birden fazla işletmeyi yönetiyorsa, sadece bu ismi
    # İÇEREN bildirim maillerini işle (yoksa hepsi aynı Instagram'a düşer).
    # Boş bırakılırsa hiçbir filtre uygulanmaz.
    REVIEW_SOURCE_BUSINESS_NAME = os.environ.get("REVIEW_SOURCE_BUSINESS_NAME", "")

    # --- Google Haritalar taraması (Gmail bildirim mailini beklemeden,
    # doğrudan işletmenin Haritalar sayfasından yeni yorumları okur -
    # opsiyonel: boş bırakılırsa bu adım tamamen atlanır, sadece Gmail
    # yolu çalışır). automation/maps_watch.py içinde detaylı açıklama var.
    GOOGLE_MAPS_URL = os.environ.get("GOOGLE_MAPS_URL", "")

    # Google, giriş yapılmamış (oturumsuz) tarayıcılara işletme sayfasının
    # Yorumlar sekmesi dahil sekme çubuğu OLMAYAN "sınırlı görünüm"ünü
    # gösteriyor (2026-08'de teşhis edildi) - bu yüzden bir Google
    # hesabının OTURUM DURUMUNU (çerezlerini) tools/save_google_session.py
    # ile bir kere kaydedip buraya (GOOGLE_STORAGE_STATE secret'ı olarak)
    # koymak GEREKİYOR, yoksa Haritalar taraması hiç çalışmaz. JSON
    # içeriğinin TAMAMI (Playwright'ın storage_state formatı) buraya gelir.
    # Boşsa maps_watch.py oturumsuz denemeye devam eder (yine sınırlı
    # görünüme takılır).
    GOOGLE_STORAGE_STATE = os.environ.get("GOOGLE_STORAGE_STATE", "")

    # --- Instagram / Meta Graph API ---
    IG_ACCESS_TOKEN = _require("IG_ACCESS_TOKEN")
    IG_USER_ID = _require("IG_USER_ID")
    GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION", "v21.0")
    # NOT: Meta düzenli aralıklarla API versiyonunu günceller.
    # developers.facebook.com/docs/graph-api/changelog adresinden
    # güncel versiyonu kontrol edip gerekirse burayı güncelle.

    # --- GitHub (üretilen görseli / durumu herkese açık bir şekilde
    # okumak/kaydetmek için) ---
    GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")  # Actions otomatik set eder: "kullanici/repo"

    # --- Çalışma davranışı ---
    MAX_REVIEWS_PER_RUN = int(os.environ.get("MAX_REVIEWS_PER_RUN", "5"))
    MIN_RATING_TO_POST = int(os.environ.get("MIN_RATING_TO_POST", "4"))
    # 4 ve 5 yıldız otomatik paylaşılır; daha düşük puanlı (veya puanı
    # maildeki metinden okunamayan) yorumlar hikayeye atılmaz, sadece
    # "işlendi" olarak işaretlenir (marka güvenliği için).

    # --- Aşağıdakiler SADECE automation/image_gen.py'yi (isteğe bağlı,
    # isim/yıldız gibi bilgileri görsele otomatik yazan eski mod) elle
    # kullanmak istersen lazım oluyor. Varsayılan akış (main.py) hazır
    # şablon havuzunu (assets/story-templates/) olduğu gibi paylaştığı
    # için bunlara ihtiyaç duymaz. ---
    BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "İşletme Adınız")
    THANK_YOU_SUBTEXT = os.environ.get(
        "THANK_YOU_SUBTEXT",
        "Değerli yorumunuz için çok teşekkür ederiz. Sizi tekrar ağırlamak için sabırsızlanıyoruz!",
    )
    ACCENT_COLOR = os.environ.get("ACCENT_COLOR", "#9a4a2b")
    LOGO_PATH = os.environ.get("LOGO_PATH", "")
