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

TARİH FİLTRESİ: Google Haritalar'da SADECE BUGÜN yapılmış yorumlar
alınır - "3 gün önce", "bir hafta önce" gibi ESKİ yorumlar (backlog'da
kalmış, bir önceki tarama başarısız olduğu için hâlâ listede görünen
vb.) burada elenir, results'a hiç eklenmez. Amaç: botun, günler önce
yapılmış bir yorumu sanki bugün gelmiş gibi hikayeye paylaşmasını
önlemek. Google'ın gösterdiği göreli zaman metni ("X saat/gün/hafta
önce") anlaşılamazsa (DOM değişmiş olabilir), YORUM YİNE DE ALINIR -
amaç, gerçekten yeni bir yorumun bir metin/DOM değişikliği yüzünden
sessizce kaybolmaması (bkz. _is_from_today).
"""

import json
import os
import re

from automation import review_key

MAX_SCROLL_ATTEMPTS = 8
STAR_ARIA_RE = re.compile(r"(\d+(?:[.,]\d+)?)")
REVIEWS_LINK_RE = re.compile(r"\d+[\.,]?\d*\s*(yorum|review|değerlendirme)", re.IGNORECASE)
RELATIVE_TIME_RE = re.compile(
    # Google Türkçe arayüzde sayıyı bazen rakamla ("3 gün önce"), bazen
    # "bir" kelimesiyle ("bir gün önce", "bir hafta önce") yazıyor -
    # ikisini de yakalıyoruz.
    r"(az önce|(?:bir|\d+)\s*(dakika|saat|gün|hafta|ay|yıl)\s*önce|dün|bugün)",
    re.IGNORECASE,
)

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

    # 0. deneme (EN GÜVENİLİR - gerçek DOM'dan DevTools ile doğrulandı,
    # 2026-08): üstteki sekme çubuğu <div role="tablist" class="RWPxGd">
    # içinde 3 <button role="tab"> var (Genel bakış / Yorumlar / Hakkında),
    # her birinin içinde görünen metni taşıyan bir "Gpq6kf" class'lı div
    # var (örn. içeriği tam olarak "Yorumlar"). aria-label tabanlı eşleşme
    # (aşağıdaki 1. deneme) teoride de tutması gerekirken headless
    # çalıştırmalarda tutarlı şekilde başarısız oluyordu - muhtemelen
    # erişilebilirlik ismi tam hesaplanmadan tıklanmaya çalışılıyordu; bu
    # yüzden burada DOĞRUDAN görünen metne (yapısal olarak) bakıyoruz.
    if _attempt(
        lambda: page.locator('div[role="tablist"] button[role="tab"]').filter(has_text="Yorumlar"),
        "tablist > button[role=tab] (metin='Yorumlar', doğrulanmış)",
    ):
        return True
    # 0b. deneme: aynı yapı ama konum bazlı (Yorumlar sekmesi doğrulanan
    # DOM'da data-tab-index="1" - Genel bakış=0, Yorumlar=1, Hakkında=2).
    # Sadece 0/0b metinle bulunamazsa devreye girer, metin eşleşmesi kırılırsa
    # (örn. Google metni değiştirirse) yine de bir şans daha verir.
    if _attempt(
        lambda: page.locator('div[role="tablist"] button[role="tab"][data-tab-index="1"]'),
        "tablist > button[data-tab-index=1] (konum bazlı)",
    ):
        return True

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
    sırayla devam edilir, önemli değil, sadece daha az verimli olur.

    NOT (2026-08, gerçek DOM dump'ı ile doğrulandı): sıralama butonunun
    kendi metni/aria-label'ı "Sırala"/"Sort" DEĞİL, o an SEÇİLİ OLAN
    değerin kendisi (örn. aria-label="En yeni", class="HQzyZ",
    aria-haspopup="true"). Yani "sırala" kelimesini arayan eski mantık,
    sıralama zaten 'En yeni' ise (ki bu işletmede varsayılan öyle
    görünüyor) hep 'bulunamadı' diyip aslında zararsız bir şekilde
    başarısız oluyordu. Önce buton zaten 'en yeni' diyorsa hiç
    tıklamadan başarılı sayıyoruz; değilse tıklayıp menüden seçiyoruz."""
    try:
        already = page.get_by_role("button", name=re.compile(r"en yeni", re.IGNORECASE))
        if already.count() > 0:
            print("[maps_watch] Sıralama zaten 'En yeni' (ekstra tıklama gerekmedi).")
            return True
    except Exception:
        pass

    sort_names = [
        re.compile(r"sırala", re.IGNORECASE),
        re.compile(r"sort", re.IGNORECASE),
    ]
    candidates = []
    for pattern in sort_names:
        candidates.append(lambda p=pattern: page.get_by_role("button", name=p))
    # Gerçek DOM'da doğrulanan class - metin/aria-label'ı değişse bile
    # (farklı işletme/dil, farklı A/B varyantı) bu class genelde sabit
    # kalıyor.
    candidates.append(lambda: page.locator('button.HQzyZ[aria-haspopup="true"]'))

    for get_locator in candidates:
        try:
            btn = get_locator()
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
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
        except Exception:
            continue
    print("[maps_watch] Sıralama değiştirilemedi, varsayılan sırayla devam ediliyor (kritik değil).")
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


def _extract_review_text(card) -> str:
    """Yorumun yazılı metnini çıkarmayı dener. Google Maps'te yorum metni
    genelde '.wiI7pd' class'lı bir span içinde oluyor (bilinen/yaygın bir
    yapı ama bu hesapta DevTools ile doğrulanmadı) - bulunamazsa yedek
    olarak kart içindeki en uzun satırı (isim/tarih gibi kısa satırları
    eleyerek) yorum metni sayıyoruz."""
    try:
        el = card.locator(".wiI7pd").first
        if el.count() > 0:
            t = el.inner_text().strip()
            if t:
                return t
    except Exception:
        pass
    try:
        text = card.inner_text()
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        # İsim, tarih, "Yararlı" gibi kısa satırları ele - yorum metni
        # genelde bunlardan belirgin şekilde daha uzun oluyor.
        candidates = [l for l in lines if len(l) > 25]
        if candidates:
            return max(candidates, key=len)
    except Exception:
        pass
    return ""


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


def _extract_relative_time_text(card) -> str:
    """Yorumun 'ne zaman yapıldığını' gösteren göreli zaman metnini
    (örn. '3 gün önce', '2 saat önce', 'az önce') kart içindeki satırlar
    arasından bulmaya çalışır. Google Maps bunun için genelde ayrı bir
    class kullanıyor ama bu hesap üzerinde DevTools ile doğrulanmadı - bu
    yüzden kırılgan bir class adına güvenmek yerine METİN DESENİYLE
    (regex) arıyoruz; Google sayfa yapısını değiştirse bile bu metin
    kalıbı (Türkçe arayüzde) büyük ihtimalle aynı kalır."""
    try:
        text = card.inner_text()
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            m = RELATIVE_TIME_RE.search(line.lower())
            if m:
                return m.group(0)
    except Exception:
        pass
    return ""


def _is_from_today(relative_time_text: str):
    """Göreli zaman metnine bakarak yorumun BUGÜN yapılıp yapılmadığını
    tahmin eder.
    Dönüş: True (bugün/az önce/X dakika-saat önce) / False (bugün değil -
    dün, X gün/hafta/ay/yıl önce) / None (metin boş ya da anlaşılamadı -
    bu durumda ÇAĞIRAN TARAF yorumu YİNE DE işleme alır, bkz. yukarıdaki
    modül notu)."""
    if not relative_time_text:
        return None
    t = relative_time_text.lower()
    if "az önce" in t or "bugün" in t:
        return True
    if "dakika önce" in t or "saat önce" in t:
        return True
    if "dün" in t:
        return False
    if "gün önce" in t or "hafta önce" in t or "ay önce" in t or "yıl önce" in t:
        return False
    return None


def fetch_reviews_from_maps(maps_url: str, business_name: str, max_reviews: int = 10,
                             storage_state: str = ""):
    """
    Dönüş: [{"source": "maps", "reviewer_name", "rating", "business", "review_key"}, ...]
    Herhangi bir adım başarısız olursa (Google sayfa yapısını değiştirdiyse,
    ağ sorunu vs.) boş liste döner - çağıran taraf (main.py) bunu Gmail
    yolunun devam etmesini engellemeyecek şekilde ele alır.

    storage_state: Config.GOOGLE_STORAGE_STATE - bir Google hesabının
    kaydedilmiş oturum durumu (Playwright storage_state formatında JSON
    metni). KESİN OLARAK GEREKLİ: 2026-08'de teşhis edildiği üzere, Google
    Haritalar OTURUM AÇILMAMIŞ tarayıcılara işletme sayfasının Genel Bakış/
    Yorumlar/Hakkında sekme çubuğu OLMAYAN "sınırlı görünüm"ünü gönderiyor
    (headless olup olmaması fark etmiyor, sadece oturum durumu önemli) - bu
    yüzden bu boşsa Yorumlar sekmesi büyük ihtimalle hiç bulunamayacak.
    Kurulum için tools/save_google_session.py'ye bak.
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

    if not storage_state:
        print("[maps_watch] UYARI: GOOGLE_STORAGE_STATE ayarlanmamış - Google Haritalar "
              "muhtemelen 'sınırlı görünüm' gösterecek ve Yorumlar sekmesi bulunamayacak. "
              "Kurulum için tools/save_google_session.py'yi çalıştır.")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context_kwargs = dict(
                locale="tr-TR",
                viewport={"width": 1366, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            if storage_state:
                # storage_state Playwright'a hem dosya yolu hem de python
                # dict/JSON-string olarak verilebilir; burada elimizde
                # doğrudan JSON METNİ var (secret olarak öyle geldi), o
                # yüzden önce dict'e çeviriyoruz.
                try:
                    context_kwargs["storage_state"] = json.loads(storage_state)
                except Exception as exc:
                    print(f"[maps_watch] UYARI: GOOGLE_STORAGE_STATE JSON olarak okunamadı "
                          f"({exc}), oturumsuz devam ediliyor.")
            context = browser.new_context(**context_kwargs)
            # navigator.webdriver=true bayrağı otomasyonu ele veren en
            # bilinen işaretlerden biri - her yeni sayfada gizliyoruz
            # (zararı yok, oturumla birlikte ekstra bir güvenlik katmanı).
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
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

            # Sekme çubuğu (Genel bakış / Yorumlar / Hakkında) JS ile geç
            # render olabiliyor - tıklamayı denemeden önce DOM'da gerçekten
            # oluşmasını bekliyoruz (aksi halde 0 eşleşme bulup gereksiz yere
            # yedek/gevşek stratejilere düşüyorduk).
            try:
                page.wait_for_selector('div[role="tablist"] button[role="tab"]', timeout=12000)
                print("[maps_watch] Sekme çubuğu (tablist) DOM'da bulundu.")
            except Exception:
                print("[maps_watch] UYARI: 12 sn içinde sekme çubuğu (tablist) görünmedi, yine de denenecek.")

            # 'Yorumlar' sekmesini açma bazen ilk denemede başarısız oluyor
            # - muhtemelen sayfa/JS tam hydrate olmadan tıklamayı deniyoruz.
            # Bu yüzden birkaç kez, aralarda ekstra bekleyerek tekrar
            # deniyoruz (pes etmeden önce).
            opened = False
            for attempt in range(1, 4):
                opened = _open_reviews_tab(page)
                if opened:
                    if attempt > 1:
                        print(f"[maps_watch] Yorumlar sekmesi {attempt}. denemede açıldı.")
                    break
                print(f"[maps_watch] Yorumlar sekmesi {attempt}. denemede açılamadı, "
                      f"biraz bekleyip tekrar denenecek.")
                page.wait_for_timeout(2500)

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
                review_text = _extract_review_text(card)
                if not name:
                    continue

                rel_time = _extract_relative_time_text(card)
                is_today = _is_from_today(rel_time)
                if is_today is False:
                    print(f"[maps_watch] '{name}' yorumu bugüne ait değil ({rel_time!r}), atlanıyor.")
                    continue
                if is_today is None:
                    print(f"[maps_watch] '{name}' yorumunun tarihi anlaşılamadı, "
                          f"yine de işleme alınıyor (güvenli taraf).")

                results.append({
                    "source": "maps",
                    "reviewer_name": name,
                    "rating": rating,
                    "review_text": review_text,
                    "business": business_name,
                    "review_key": review_key.make_key(name, rating, business_name),
                })

            print(f"[maps_watch] Sonuç: {len(results)} yorum çıkarıldı.")
            browser.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[maps_watch] Tarama sırasında hata (bu run için atlanıyor): {exc}")
        return results

    return results
