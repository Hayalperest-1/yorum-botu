"""
TEK SEFERLİK kurulum aracı: Google Haritalar'ın botun gördüğü "sınırlı
görünüm" sorununu çözmek için, bir Google hesabının OTURUM DURUMUNU
(çerezlerini) kaydeder.

NEDEN GEREKLİ (2026-08'de teşhis edildi): Google Haritalar, hiçbir hesaba
giriş yapılmamış tarayıcılara işletme sayfasının Genel Bakış/Yorumlar/
Hakkında sekme çubuğu OLMAYAN, "sınırlı görünüm" adı verilen basitleştirilmiş
bir sürümünü gönderiyor - bu sınırlı görünümde Yorumlar sekmesi diye bir şey
yok, bu yüzden bot yorumları hiç bulamıyordu. Çözüm: bir Google hesabıyla
GERÇEKTEN giriş yapılmış bir tarayıcı oturumunun çerezlerini bir kere alıp,
botun GitHub Actions'ta her çalıştığında bu oturumu "geri yüklemesini"
sağlamak.

NASIL ÇALIŞIR:
  1) Bu scripti kendi bilgisayarında çalıştırıyorsun (çift tıkla: yanındaki
     "oturum_kaydet.bat" dosyası - ya da elle "python tools/save_google_session.py").
  2) GERÇEK bir Chrome penceresi açılıyor (headless DEĞİL, sen görebiliyorsun).
  3) O pencerede Google hesabınla NORMAL ŞEKİLDE giriş yapıyorsun - şifreni,
     2 adımlı doğrulama kodunu vs. SEN yazıyorsun, bu script hiçbirini
     görmüyor/kaydetmiyor, sadece giriş TAMAMLANDIKTAN SONRAKİ çerezleri alıyor.
  4) Giriş yaptıktan sonra bu pencereye (terminale) dönüp Enter'a basıyorsun.
  5) Script "tools/google_session.json" dosyasını oluşturuyor.

SONRA NE YAPACAKSIN (ÇOK ÖNEMLİ):
  - "tools/google_session.json" dosyasının İÇERİĞİNİ (tamamını, bir metin
    editörüyle açıp kopyala) GitHub'da repo -> Settings -> Secrets and
    variables -> Actions -> "New repository secret" ile "GOOGLE_STORAGE_STATE"
    adında yeni bir secret olarak ekle.
  - Bu dosyayı ASLA GitHub'a normal bir dosya olarak commit'leme/push'lama -
    içinde oturum çerezlerin var, bu neredeyse şifren kadar hassas bir bilgi
    (.gitignore'a zaten eklendi, güvenlik için, ama yine de dikkatli ol).
  - İstersen bu iş için ayrı, sadece bu işletmeyi yönetmek için kullandığın
    ikinci bir Google hesabı da kullanabilirsin - ana kişisel hesabını
    kullanmak zorunda değilsin.

NOT: Google oturumları bazen (aylar sonra, şifre değişirse, şüpheli aktivite
algılanırsa vs.) geçersiz olabilir - böyle bir durumda bot loglarında yine
"sınırlı görünüm" uyarısı görürsün, o zaman bu scripti tekrar çalıştırıp
GOOGLE_STORAGE_STATE secret'ını güncellemen yeterli.
"""

import json
import os
import sys

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "google_session.json")


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("HATA: playwright kurulu değil. Önce şunu çalıştır:")
        print("  pip install -r requirements.txt")
        print("  playwright install chromium")
        sys.exit(1)

    print("=" * 70)
    print("Google oturumu kaydetme aracı")
    print("=" * 70)
    print()
    print("Şimdi bir Chrome penceresi açılacak. O pencerede:")
    print("  1) Google hesabınla (ya da bu iş için ayırdığın hesapla) giriş yap")
    print("  2) Giriş tamamlanınca (Google Haritalar ana sayfasını görene kadar)")
    print("     BU PENCEREYE (terminale) geri dön ve Enter'a bas")
    print()
    input("Hazır olduğunda Enter'a basıp devam et...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="tr-TR", viewport={"width": 1366, "height": 900})
        page = context.new_page()
        page.goto("https://www.google.com/maps", timeout=30000)

        print()
        print("Tarayıcı penceresi açıldı. Orada Google hesabınla giriş yap")
        print("(sağ üstteki 'Oturum açın' butonuna tıkla).")
        print()
        input("Giriş yaptıktan SONRA buraya dönüp Enter'a bas...")

        # Giriş sonrası oturumun oturmasi icin kisa bir bekleme.
        page.wait_for_timeout(2000)

        state = context.storage_state()
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f)

        print()
        print(f"Kaydedildi: {OUTPUT_PATH}")
        print()
        print("ŞİMDİ ŞUNU YAP:")
        print(f"  1) '{OUTPUT_PATH}' dosyasını bir metin editörüyle aç, İÇERİĞİNİN TAMAMINI kopyala")
        print("  2) GitHub'da repo -> Settings -> Secrets and variables -> Actions")
        print("  3) 'New repository secret' -> İsim: GOOGLE_STORAGE_STATE -> Değer: kopyaladığın JSON")
        print("  4) Kaydet")
        print()
        print("Bu dosyayı ASLA GitHub'a normal dosya olarak commit'leme (.gitignore'da zaten hariç tutuldu).")

        browser.close()


if __name__ == "__main__":
    main()
