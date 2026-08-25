"""
Google Haritalar'daki işletme sayfasını (Playwright ile, gerçek bir tarayıcı
açıp) tarayarak en yeni yorumları okur. Gmail bildirim mailini BEKLEMEDEN
çalışır - Google bazen bildirim mailini geç (hatta hiç) gönderebiliyor,
bu yöntem doğrudan Google Haritalar'daki güncel duruma bakar.

ÖNEMLİ - bu resmi bir API DEĞİL, Google'ın herkese açık sayfasını okuyor:
  - Google sayfa tasarımını değiştirirse bu kod bozulabilir (seçiciler
    (selector) eskir). Böyle bir durumda main.py'nin loglarında
    "[maps_watch]" ile başlayan satırlara bakıp burayı güncellemek gerekir.
  - Her adımda debug_screenshots/ klasörüne bir ekran görüntüsü kaydediyoruz
    (GitHub Actions'ta "workflow artifact" olarak indirilebilir) - bir şey
    ters giderse, botun tam olarak hangi ekranda takıldığını görebiliriz.
  - Bu yüzden her adım try/except ile korunuyor: bir şey ters giderse tüm
    çalıştırma çökmüyor, sadece boş liste dönüyor ve Gmail yolu (varsa)
    devam ediyor.
  - Kart/onay/Google Cloud projesi GEREKTİRMEZ, tamamen ücretsizdir.

Dönüş formatı gmail_watch.fetch_new_reviews ile aynı: her yorum için
{"source", "reviewer_name", "rating", "business", "review_key"} sözlüğü.
review_key, iki kaynaktan (Gmail + Haritalar) aynı yorum gelirse ikinci
kez paylaşılmasını önlemek için review_key.py ile üretiliyor.
"""

import os
import re

from automation import review_key

MAX_SCROLL_ATTEMPTS = 8
STAR_ARIA_RE = re.compile(r"(\d+(?:[.,]\d+)?)")
REVIEWS_LINK_RE = re.compile(r"\d+[\.,]?\d*\s*(yorum|review|değerlendirme)", re.IGNORECASE)

DEBUG_DIR = "debug_screenshots"


def _shot(page, name: str) -> None:
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        path = os.path.join(DEBUG_DIR, f"{name}.png")
        page.screenshot(path=path)
        print(f"[maps_watch] ekran görüntüsü kaydedildi: {path}")
    except Exception as exc:  # noqa: BLE001
        print(f"[maps_watch] ekran görüntüsü alınamadı ({name}): {exc}")


def _accept_or_dismiss_consent(page) -> bool:
    """Google'ın çerez/onay ekranını kapatmayı dener (birden fazla dil/metin
    varyasyonunu sırayla dener, hiçbiri bulunamazsa sessizce devam eder)."""
    candidates = [
        "Tümünü reddet", "Reject all", "Reject All",
        "Tümünü kabul et", "Accept all", "Accept All",
        "Kabul Et", "I agree", "Kabul ediyorum",
    ]
    for text in candidates:
        try:
            btn = page.get_by_role("button", name=text, exact=False)
            if btn.count() > 0:
                btn.first.click(timeout=3000)
                page.wait_for_timeout(1000)
                print(f"[maps_watch] onay ekranı kapatıldı ('{text}' butonuna tıklandı).")
                return True
        except Exception:
            continue
    print("[maps_watch] onay ekranı bulunamadı (muhtemelen zaten yoktu, sorun değil).")
    return False


def _reviews_panel_visible(page) -> bool:
    """Yorumlar paneli gerçekten açıldı mı diye kontrol eder (tıklanan öğe
    yanlış bir şeyse - ör. 'Yorum yaz' butonu - bunu yakalamak için)."""
    try:
        if page.locator('div.jftiEf[data-review-id]').count() > 0:
            return True
        if page.locator('div[role="feed"]').count() > 0:
            return True
        if page.get_by_role("button", name=re.compile(r"sırala|sort", re.IGNORECASE)).count() > 0:
            return True
    except Exception:
        pass
    return False


def _open_reviews_tab(page) -> bool:
    """İşletme sayfasında 'Yorumlar' sekmesine/bağlantısına tıklamayı dener.
    Birden fazla strateji sırayla denenir çünkü Google Haritalar düzeni
    hesaba/bölgeye göre değişebiliyor. Her tıklamadan sonra gerçekten
    yorumlar paneli açıldı mı diye DOĞRULUYORUZ - çünkü gevşek metin
    eşleşmeleri ("yorum" geçen herhangi bir buton) yanlışlıkla 'Yorum yaz'
    gibi alakasız bir butona tıklayabilir; bu durumda bir sonraki
    stratejiye geçiyoruz (Escape ile olası bir diyaloğu kapatıp)."""
    patterns = [
        re.compile(r"yorum", re.IGNORECASE),
        re.compile(r"review", re.IGNORECASE),
        re.compile(r"değerlendirme", re.IGNORECASE),
    ]

    def _attempt(get_locator, label) -> bool:
        try:
            loc = get_locator()
            has_match = loc.count() if hasattr(loc, "count") else 0
            if has_match:
                loc.first.click(timeout=5000)
                page.wait_for_timeout(1500)
                if _reviews_panel_visible(page):
                    print(f"[maps_watch] Yorumlar paneli açıldı: {label}")
                    return True
                print(f"[maps_watch] '{label}' tıklandı ama yorumlar paneli görünmedi, başka yöntem deneniyor.")
                try:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(300)
                except Exception:
                    pass
        except Exception as exc:
            print(f"[maps_watch] '{label}' denemesi başarısız: {exc}")
        return False

    # 1. deneme: role="tab" (en güvenilir - üstteki Genel bakış/Yorumlar/Hakkında sekmeleri)
    for pattern in patterns:
        if _attempt(lambda p=pattern: page.get_by_role("tab", name=p), f"tab /{pattern.pattern}/"):
            return True

    # 2. deneme: "4,9 yıldız, 128 yorum" gibi sayı+"yorum" içeren tıklanabilir öğe
    # (bu, işletme adının hemen altındaki yıldız/yorum-sayısı özetidir ve
    # tıklanınca doğrudan yorumlar paneline geçer - genelde en güvenilir 2.
    # seçenek, "Yorum yaz" gibi alakasız butonlarla karışmaz çünkü rakam içerir)
    if _attempt(lambda: page.get_by_role("button", name=REVIEWS_LINK_RE), "sayı+yorum (button)"):
        return True
    if _attempt(lambda: page.get_by_text(REVIEWS_LINK_RE), "sayı+yorum (metin)"):
        return True

    # 3. deneme: tam "Yorumlar" metnini taşıyan herhangi bir öğe (rol fark etmez)
    if _attempt(lambda: page.get_by_text("Yorumlar", exact=True), "tam 'Yorumlar' metni"):
        return True

    # 4. deneme (son çare - en riskli): "yorum" geçen herhangi bir buton.
    # Bu "Yorum yaz" gibi alakasız butonlara da tıklayabilir, bu yüzden en
    # sona bırakıldı ve yine de _reviews_panel_visible ile doğrulanıyor.
    for pattern in patterns:
        if _attempt(lambda p=pattern: page.get_by_role("button", name=p), f"gevşek buton /{pattern.pattern}/"):
            return True

    print("[maps_watch] 'Yorumlar' sekmesi HİÇBİR yöntemle bulunamadı (veya tıklanan öğe doğru paneli açmadı).")
    return False


def _sort_by_newest(page) -> bool:
    """Yorumları 'En yeni' sıraya almayı dener - başarısız olursa varsayılan
    sırayla (genelde 'En alakalı') devam edilir, önemli değil, sadece daha
    az verimli olur."""
    sort_names = [
        re.compile(r"sırala", re.IGNORECASE),
        re.compile(r"sort", re.IGNORECASE),
    ]
    for pattern in sort_names:
        try:
            btn = page.get_by_role("button", name=pattern)
            if btn.count() > 0:
                btn.first.click(timeout=4000)
                page.wait_for_timeout(800)
                for newest in [re.compile(r"en yeni", re.IGNORECASE), re.compile(r"newest", re.IGNORECASE)]:
                    option = page.get_by_role("menuitemradio", name=newest)
                    if option.count() == 0:
                        option = page.get_by_text(newest)
                    if option.count() > 0:
                        option.first.click(timeout=4000)
                        page.wait_for_timeout(1500)
                        print("[maps_watch] Sıralama 'En yeni' olarak değiştirildi.")
                        return True
        except Exception:
            continue
    print("[maps_watch] Sıralama değiştirilemedi, varsayılan sırayla devam ediliyor.")
    return False


def _extract_rating(card) -> int:
    try:
        el = card.locator('[aria-label*="yıldız"], [aria-label*="star"], [role="img"]').first
        aria = el.get_attribute("aria-label") or ""
        m = STAR_ARIA_RE.search(aria)
        if m:
            return int(round(float(m.group(1).replace(",", "."))))
    except Exception:
        pass
    return 0


def _extract_name(card) -> str:
    # Gerçek Google Haritalar sayfasından incelenerek doğrulandı: yorum
    # kartının dış div'inde aria-label doğrudan kullanıcının adını taşıyor
    # (örn. aria-label="Ecmel Köylü") - bu inner_text ile ilk satırı almaktan
    # çok daha güvenilir.
    try:
        aria_name = card.get_attribute("aria-label")
        if aria_name and aria_name.strip():
            return aria_name.strip()
    except Exception:
        pass
    try:
        name_el = card.locator(".d4r55").first
        if name_el.count() > 0:
            return name_el.inner_text().strip()
    except Exception:
        pass
    try:
        text = card.inner_text()
        first_line = text.strip().split("\n")[0].strip()
        if first_line:
            return first_line
    except Exception:
        pass
    return ""


def fetch_reviews_from_maps(maps_url: str, business_name: str, max_reviews: int = 10):
    """
    Dönüş: [{"source": "maps", "reviewer_name", "rating", "business", "review_key"}, ...]
    Herhangi bir adım başarısız olursa (Google sayfa yapısını değiştirdiyse,
    ağ sorunu vs.) boş liste döner - çağıran taraf (main.py) bunu Gmail
    yolunun devam etmesini engellemeyecek şekilde ele alır.
    """
    if not maps_url:
        print("[maps_watch] GOOGLE_MAPS_URL ayarlanmamış, bu adım atlanıyor.")
        return []

    results = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[maps_watch] playwright kurulu değil, bu adım atlanıyor.")
        return []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                locale="tr-TR",
                viewport={"width": 1366, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            print(f"[maps_watch] Sayfaya gidiliyor: {maps_url}")
            page.goto(maps_url, timeout=30000, wait_until="domcontentloaded")

            try:
                page.wait_for_selector("h1", timeout=15000)
            except Exception:
                print("[maps_watch] UYARI: 15 sn içinde başlık (h1) yüklenmedi, devam ediliyor.")

            page.wait_for_timeout(2000)
            print(f"[maps_watch] Yönlendirilen adres: {page.url}")
            print(f"[maps_watch] Sayfa başlığı: {page.title()}")
            _shot(page, "1_initial")

            _accept_or_dismiss_consent(page)
            page.wait_for_timeout(500)
            _shot(page, "2_after_consent")

            opened = _open_reviews_tab(page)
            _shot(page, "3_after_reviews_tab")
            if not opened:
                print("[maps_watch] Yorumlar sekmesi açılamadığı için taramaya devam edilemiyor.")
                browser.close()
                return results

            _sort_by_newest(page)
            _shot(page, "4_after_sort")

            # Yorum listesi kaydırılabilir bir alanda (role=feed) yükleniyor,
            # daha fazla yorum görmek için birkaç kez aşağı kaydırıyoruz.
            feed = page.locator('div[role="feed"]')
            feed_count = feed.count()
            print(f"[maps_watch] role=feed bulunan alan sayısı: {feed_count}")
            for _ in range(MAX_SCROLL_ATTEMPTS):
                try:
                    if feed_count > 0:
                        feed.first.evaluate("el => el.scrollBy(0, 800)")
                    else:
                        page.mouse.wheel(0, 800)
                    page.wait_for_timeout(600)
                except Exception:
                    break

            _shot(page, "5_after_scroll")

            # Gerçek sayfa incelenerek doğrulandı: yorum kartının dış div'i
            # "jftiEf" class'ını ve data-review-id özniteliğini birlikte
            # taşıyor (data-review-id tek başına, aynı yorumun içindeki
            # reviewerLink/actionMenu butonlarında da tekrarlandığı için
            # tek başına yeterince spesifik değil).
            cards = page.locator("div.jftiEf[data-review-id]")
            count = cards.count()
            print(f"[maps_watch] {count} yorum kartı bulundu (div.jftiEf[data-review-id] ile).")

            if count == 0:
                # Yedek deneme: class ismi değişmiş olabilir, sadece
                # data-review-id'ye göre dene (daha az spesifik ama en
                # azından teşhis için kaç aday öğe olduğunu görürüz).
                fallback = page.locator("div[data-review-id]")
                fb_count = fallback.count()
                print(f"[maps_watch] Yedek arama: sadece data-review-id ile bulunan div sayısı: {fb_count}")
                if fb_count > 0:
                    cards = fallback
                    count = fb_count

            for i in range(min(count, max_reviews)):
                card = cards.nth(i)
                name = _extract_name(card)
                rating = _extract_rating(card)
                if not name:
                    continue
                results.append({
                    "source": "maps",
                    "reviewer_name": name,
                    "rating": rating,
                    "business": business_name,
                    "review_key": review_key.make_key(name, rating, business_name),
                })

            print(f"[maps_watch] Sonuç: {len(results)} yorum çıkarıldı.")
            browser.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[maps_watch] Tarama sırasında hata (bu run için atlanıyor): {exc}")
        return results

    return results
