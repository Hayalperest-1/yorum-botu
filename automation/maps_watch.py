"""
Google Haritalar'daki işletme sayfasını (Playwright ile, gerçek bir tarayıcı
açıp) tarayarak en yeni yorumları okur. Gmail bildirim mailini BEKLEMEDEN
çalışır - Google bazen bildirim mailini geç (hatta hiç) gönderebiliyor,
bu yöntem doğrudan Google Haritalar'daki güncel duruma bakar.

ÖNEMLİ - bu resmi bir API DEĞİL, Google'ın herkese açık sayfasını okuyor:
  - Google sayfa tasarımını değiştirirse bu kod bozulabilir (seçiciler
    (selector) eskir). Böyle bir durumda main.py'nin loglarında
    "[maps_watch]" ile başlayan satırlara bakıp burayı güncellemek gerekir.
  - Bu yüzden her adım try/except ile korunuyor: bir şey ters giderse tüm
    çalıştırma çökmüyor, sadece boş liste dönüyor ve Gmail yolu (varsa)
    devam ediyor.
  - Kart/onay/Google Cloud projesi GEREKTİRMEZ, tamamen ücretsizdir.

Dönüş formatı gmail_watch.fetch_new_reviews ile aynı: her yorum için
{"source", "reviewer_name", "rating", "business", "review_key"} sözlüğü.
review_key, iki kaynaktan (Gmail + Haritalar) aynı yorum gelirse ikinci
kez paylaşılmasını önlemek için review_key.py ile üretiliyor.
"""

import re

from automation import review_key

MAX_SCROLL_ATTEMPTS = 8
STAR_ARIA_RE = re.compile(r"(\d+(?:[.,]\d+)?)")


def _accept_or_dismiss_consent(page):
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
                return
        except Exception:
            continue


def _open_reviews_tab(page):
    """İşletme sayfasında 'Yorumlar' sekmesine/bağlantısına tıklamayı dener."""
    patterns = [
        re.compile(r"yorum", re.IGNORECASE),
        re.compile(r"review", re.IGNORECASE),
        re.compile(r"değerlendirme", re.IGNORECASE),
    ]
    for pattern in patterns:
        try:
            tab = page.get_by_role("tab", name=pattern)
            if tab.count() > 0:
                tab.first.click(timeout=5000)
                page.wait_for_timeout(1500)
                return True
        except Exception:
            continue
    # Bazı düzenlerde yorum sayısı bir butona basılabilir metin olarak duruyor
    for pattern in patterns:
        try:
            btn = page.get_by_role("button", name=pattern)
            if btn.count() > 0:
                btn.first.click(timeout=5000)
                page.wait_for_timeout(1500)
                return True
        except Exception:
            continue
    return False


def _sort_by_newest(page):
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
                        return True
        except Exception:
            continue
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
            page.goto(maps_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            _accept_or_dismiss_consent(page)

            opened = _open_reviews_tab(page)
            if not opened:
                print("[maps_watch] 'Yorumlar' sekmesi bulunamadı, sayfa yapısı değişmiş olabilir.")

            _sort_by_newest(page)

            # Yorum listesi kaydırılabilir bir alanda (role=feed) yükleniyor,
            # daha fazla yorum görmek için birkaç kez aşağı kaydırıyoruz.
            feed = page.locator('div[role="feed"]')
            for _ in range(MAX_SCROLL_ATTEMPTS):
                try:
                    if feed.count() > 0:
                        feed.first.evaluate("el => el.scrollBy(0, 800)")
                    else:
                        page.mouse.wheel(0, 800)
                    page.wait_for_timeout(600)
                except Exception:
                    break

            cards = page.locator("div[data-review-id]")
            count = cards.count()
            print(f"[maps_watch] {count} yorum kartı bulundu.")

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

            browser.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[maps_watch] Tarama sırasında hata (bu run için atlanıyor): {exc}")
        return results

    return results
