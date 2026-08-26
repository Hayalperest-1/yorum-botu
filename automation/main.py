"""
Ana akış - bu dosya her tetiklendiğinde (15 dakikada bir, GitHub Actions
üzerinden) çalışır:

  1) İki kaynaktan yeni yorumları toplar:
     a) Google Haritalar taraması (maps_watch.py) - Gmail bildirimini
        BEKLEMEDEN, doğrudan işletmenin Haritalar sayfasından okur.
        GOOGLE_MAPS_URL ayarlanmadıysa bu adım atlanır.
     b) Gmail'den, Google'ın gönderdiği "X, İşletme için yorum yaptı"
        bildirim mailleri (gmail_watch.py) - Haritalar taraması bir
        şekilde başarısız olursa ya da devre dışıysa yedek/tamamlayıcı.
     İki kaynaktan da aynı yorum gelirse (review_key eşleşirse) SADECE
     BİR KERE işlenir, iki kere paylaşılmaz.
  2) Puanı yeterince yüksekse (varsayılan 4+): assets/story-templates/
     klasöründeki hazır görsel/video havuzundan SIRADAKİ dosyayı al,
     Instagram hikayesine olduğu gibi paylaş, sırayı bir ilerlet
  3) Yorum metni henüz yoksa (genelde Gmail kaynaklı) hemen paylaşmak
     yerine harita taramasının onu metniyle bulmasını bekler (en fazla
     MAX_TEXT_WAIT_ATTEMPTS çalıştırma boyunca) - bu bekleme, o yorum bu
     çalıştırmada YENİDEN TOPLANMASA BİLE ilerler (aşağıdaki "pending
     reviews yaşlandırma" adımı) - eskiden bu adım eksikti ve bir yorumun
     Gmail maili "işlendi" sayılıp bir daha hiç taranmadığı, Haritalar da
     bulamadığı durumda o yorum sonsuza kadar beklemede takılı kalıyordu.
  4) İşlenen her yorumun kimliğini (review_key, ve varsa Gmail
     message_id) state.json'a ekle (bir daha "yeni" sayılmasın diye) ve
     tek seferde depoya kaydet

NOT: Bu akış Google'a OTOMATİK yanıt yazmıyor (Business Profile API'nin
kısıtlı/onaylı erişimi olmadan bu mümkün değil) - yorumu Google üzerinden
yanıtlamak hâlâ elle yapman gereken bir adım.
"""

import sys
import time

from dotenv import load_dotenv

# Yerelde ".env" dosyası varsa ortam değişkenlerini oradan yükler
# (GitHub Actions'ta .env dosyası olmadığı için burası hiçbir şey yapmaz,
# secrets zaten ortam değişkeni olarak geliyor). Config'i içeri
# aktarmadan ÖNCE çalışması şart, çünkü Config değerleri import anında
# okuyor.
load_dotenv()

import os

from automation.config import Config
from automation.instagram import InstagramClient
from automation import template_queue
from automation import state_store
from automation import gmail_watch
from automation import maps_watch
from automation import image_gen
from automation.git_publish import raw_url_for, commit_and_push

GENERATED_DIR = "assets/generated"

# Bir yorumun metni yoksa (genelde Gmail kaynaklı - Gmail bildirim maili
# yorumun yazılı içeriğini hiç vermiyor), bunu METİNSİZ hemen paylaşmak
# yerine harita taramasının o yorumu metniyle bulmasını bekliyoruz. Bot
# 15 dakikada bir çalıştığı için, bu sayı x 15 dakika kadar bekler (6 =
# yaklaşık 1,5 saat) - o kadar süre içinde de harita taraması bulamazsa,
# sonsuza kadar bekletmemek için elimizdeki bilgiyle (metinsiz) paylaşır.
MAX_TEXT_WAIT_ATTEMPTS = 6


def _collect_new_reviews(cfg, processed_message_ids: set, processed_review_keys: set):
    """İki kaynaktan gelen yorumları birleştirir, daha önce işlenmiş
    olanları (message_id VEYA review_key ile eşleşenleri) çıkarır."""
    combined = {}  # review_key -> review dict (ilk gelen kazanır)

    # a) Google Haritalar (varsa) - daha hızlı, mail beklemez
    try:
        maps_reviews = maps_watch.fetch_reviews_from_maps(
            maps_url=cfg.GOOGLE_MAPS_URL,
            business_name=cfg.REVIEW_SOURCE_BUSINESS_NAME or "İşletme",
            storage_state=cfg.GOOGLE_STORAGE_STATE,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[main] Haritalar taraması beklenmedik şekilde hata verdi, atlanıyor: {exc}", file=sys.stderr)
        maps_reviews = []

    for r in maps_reviews:
        if r["review_key"] in processed_review_keys:
            continue
        combined.setdefault(r["review_key"], r)

    # b) Gmail bildirimleri - yedek/tamamlayıcı
    gmail_reviews = gmail_watch.fetch_new_reviews(
        gmail_address=cfg.GMAIL_ADDRESS,
        app_password=cfg.GMAIL_APP_PASSWORD,
        already_processed=processed_message_ids,
        business_filter=cfg.REVIEW_SOURCE_BUSINESS_NAME,
    )
    for r in gmail_reviews:
        if r["review_key"] in processed_review_keys:
            continue
        combined.setdefault(r["review_key"], r)

    return list(combined.values())


def _post_review_to_instagram(review, cfg, ig, next_template_index):
    """Tek bir yorumu (rating yeterince yüksekse) Instagram hikayesine
    paylaşır. Hem normal (bu run'da yeni toplanan) yorumlar hem de
    bekleme süresi dolduğu için metinsiz paylaşılan eski yorumlar için
    ORTAK kod yolu - iki yerde aynı mantığı kopyalamamak için ayrıldı.
    Dönüş: (posted_or_skipped_ok: bool, yeni next_template_index)."""
    reviewer_name = review["reviewer_name"]
    rating = review["rating"]

    if rating >= cfg.MIN_RATING_TO_POST:
        template = template_queue.get_template_at(next_template_index)
        print(f"Sıradaki şablon: {template['filename']} ({template['index'] + 1}/{template['total']})")

        if template["type"] == "image":
            # Görsel şablonun üzerine isim + yıldız + yorum metni +
            # teşekkür mesajını yazıp yeni bir dosya olarak üretiyoruz.
            # Instagram bu dosyayı internetten kendisi indireceği için,
            # önce depoya commit'leyip PUSH'lamamız gerekiyor (push
            # tamamlanmadan raw.githubusercontent.com adresi çalışmaz) -
            # bu yüzden burada state.json'dan BAĞIMSIZ, ayrı bir commit
            # atılıyor.
            safe_key = "".join(c for c in review["review_key"] if c.isalnum())[:16]
            output_path = os.path.join(GENERATED_DIR, f"{safe_key}.jpg")
            image_gen.generate_story_image(
                template_path=template["path"],
                reviewer_name=reviewer_name,
                rating=rating,
                review_text=review.get("review_text", ""),
                thank_you_text=cfg.THANK_YOU_SUBTEXT,
                output_path=output_path,
            )
            commit_and_push(
                [output_path],
                f"generated: {reviewer_name} icin hikaye gorseli",
            )
            media_url = raw_url_for(output_path, cfg.GITHUB_REPOSITORY)
            is_video = False
        else:
            # Video şablonların üzerine otomatik yazı ekleme (ffmpeg/
            # moviepy gerektirir) henüz yapılmıyor - video olduğu gibi
            # paylaşılır.
            media_url = raw_url_for(template["path"], cfg.GITHUB_REPOSITORY)
            is_video = True

        media_id = ig.post_story(media_url, is_video=is_video)
        print(f"Instagram hikayesine paylaşıldı: {media_id}")
        next_template_index = template["index"] + 1

        # Art arda çok hızlı (aralıksız) paylaşım isteği göndermek Meta'nın
        # kötüye kullanım/istismar korumasını tetikleyip "API access
        # blocked" hatası verdirebiliyor (bir çalıştırmada birden fazla
        # bekleyen yorum aynı anda paylaşılırken yaşandı). Her başarılı
        # paylaşımdan sonra kısa bir süre bekleyerek isteklerin arasını
        # açıyoruz.
        time.sleep(8)
    else:
        print(f"Puan {rating}, {cfg.MIN_RATING_TO_POST} altında (ya da okunamadı) -> hikayeye paylaşılmadı.")

    return True, next_template_index


def main():
    cfg = Config

    state = state_store.load()
    processed_message_ids = set(state.get("processed_message_ids", []))
    processed_review_keys = set(state.get("processed_review_keys", []))
    pending_reviews = dict(state.get("pending_reviews", {}))

    reviews = _collect_new_reviews(cfg, processed_message_ids, processed_review_keys)

    print(f"{len(reviews)} yeni yorum bulundu, en fazla {cfg.MAX_REVIEWS_PER_RUN} tanesi işlenecek."
          if reviews else "Bu run'da yeni yorum toplanamadı (Gmail/Haritalar'dan).")

    ig = None  # sadece gerçekten paylaşım yapmamız gerekirse kuruyoruz

    def _get_ig():
        nonlocal ig
        if ig is None:
            ig = InstagramClient(
                access_token=cfg.IG_ACCESS_TOKEN,
                ig_user_id=cfg.IG_USER_ID,
                api_version=cfg.GRAPH_API_VERSION,
            )
        return ig

    next_template_index = state.get("next_template_index", 0)
    newly_processed_message_ids = []
    newly_processed_review_keys = []
    processed = 0

    # ÖNEMLİ: bu sayaç, önceki sürümdeki "processed" (SADECE BAŞARILI
    # paylaşımları sayan) sayacının aksine, Instagram'a paylaşım için
    # yapılan HER DENEMEYİ (başarılı ya da başarısız fark etmez) sayar.
    # Eskiden "processed" kullanıldığı için, bir çalıştırmada art arda
    # hatalar oluştuğunda (ör. "API access blocked") limit HİÇ dolmuyor,
    # bot elindeki TÜM birikmiş yorumları (ör. 10 tanesini) art arda,
    # duraksamadan denemeye devam ediyordu - bu da muhtemelen Meta'nın
    # kötüye kullanım korumasını tetikleyen "burst" (patlama halinde
    # istek) durumuna yol açtı. Artık limit, denemelerin SAYISINA göre
    # duruyor.
    attempts_this_run = 0
    state_changed = False

    # Bu run'da "görülen" (ele alınan) review_key'ler - aşağıdaki pending
    # yaşlandırma adımında bunları BİR DAHA sayaç ilerletmemek için
    # kullanılıyor (aksi halde bir yorumun deneme sayısı bir run içinde
    # iki kere artabilirdi).
    touched_this_run = set()

    for review in reviews:
        if attempts_this_run >= cfg.MAX_REVIEWS_PER_RUN:
            print("Bu çalıştırma için işlem limiti doldu, kalanlar bir sonraki çalıştırmada işlenecek.")
            break

        reviewer_name = review["reviewer_name"]
        rating = review["rating"]
        review_key_val = review["review_key"]
        has_text = bool((review.get("review_text") or "").strip())
        touched_this_run.add(review_key_val)

        print(f"İşleniyor ({review['source']}): {reviewer_name} - {rating} yıldız ({review['business']})")

        if not has_text:
            prior_attempts = pending_reviews.get(review_key_val, {}).get("attempts", 0)
            attempts = prior_attempts + 1
            if attempts < MAX_TEXT_WAIT_ATTEMPTS:
                pending_reviews[review_key_val] = {
                    "attempts": attempts,
                    "reviewer_name": reviewer_name,
                    "rating": rating,
                    "business": review.get("business", ""),
                }
                print(f"  -> Yorum metni henüz yok (kaynak: {review['source']}), harita taramasının "
                      f"bulması bekleniyor (deneme {attempts}/{MAX_TEXT_WAIT_ATTEMPTS}) -> BU RUN'DA PAYLAŞILMADI.")
                # Aynı Gmail mailini her run'da yeniden taramamak için
                # message_id'yi işlendi say - review_key'i DEĞİL (o hâlâ
                # pending_reviews'te bekliyor, harita bulunca ya da limit
                # dolunca aşağıdaki "pending yaşlandırma" adımıyla
                # işlenecek - Gmail'den bir daha HİÇ görünmese bile).
                if review.get("source") == "gmail" and review.get("message_id"):
                    newly_processed_message_ids.append(review["message_id"])
                state_changed = True
                continue
            else:
                print(f"  -> {MAX_TEXT_WAIT_ATTEMPTS} denemede de yorum metni bulunamadı, "
                      f"metin OLMADAN paylaşılıyor.")
                pending_reviews.pop(review_key_val, None)
                state_changed = True
        elif review_key_val in pending_reviews:
            # Bekleyen bir yorumun metni artık bulundu (harita taraması
            # başarılı oldu) - beklemeden çık.
            pending_reviews.pop(review_key_val, None)
            state_changed = True

        attempts_this_run += 1
        try:
            _, next_template_index = _post_review_to_instagram(review, cfg, _get_ig(), next_template_index)

            newly_processed_review_keys.append(review["review_key"])
            if review.get("source") == "gmail" and review.get("message_id"):
                newly_processed_message_ids.append(review["message_id"])
            state_changed = True
            processed += 1

        except Exception as exc:  # noqa: BLE001
            # Bir yorumda hata olsa bile diğerlerini işlemeye devam et;
            # bu yorumu "işlendi" olarak işaretlemediğimiz için bir
            # sonraki çalıştırmada tekrar denenecek.
            print(f"HATA ({reviewer_name}): {exc}", file=sys.stderr)

    # --- Pending (metin bekleyen) yorumları yaşlandır ---
    # Bu run'da hiç görülmeyen (ne Haritalar ne Gmail tarafından yeniden
    # toplanmayan) bekleyen yorumlar da olsa bile, "bir çalıştırma daha
    # geçti" sayılır ve deneme sayaçları ilerletilir. Süresi dolanlar
    # ARTIK BURADAN, elimizdeki (isim/puan/işletme) bilgisiyle metinsiz
    # paylaşılır - eskiden bu adım yoktu, bu yüzden Gmail'i bir daha hiç
    # görünmeyen ve Haritalar'ın da bulamadığı yorumlar sonsuza kadar
    # "bekliyor" durumunda donup kalıyordu.
    for review_key_val, info in list(pending_reviews.items()):
        if review_key_val in touched_this_run:
            continue  # bu run'da zaten normal akışta ele alındı
        if attempts_this_run >= cfg.MAX_REVIEWS_PER_RUN:
            print("İşlem limiti doldu, bekleyen yorumların yaşlandırılması bir sonraki çalıştırmaya kaldı.")
            break

        attempts = info.get("attempts", 0) + 1
        reviewer_name = info.get("reviewer_name", "")
        rating = info.get("rating", 0)
        business = info.get("business", "")

        if attempts < MAX_TEXT_WAIT_ATTEMPTS:
            pending_reviews[review_key_val] = {**info, "attempts": attempts}
            print(f"[pending] {reviewer_name} hâlâ bekliyor (deneme {attempts}/{MAX_TEXT_WAIT_ATTEMPTS}), "
                  f"bu run'da yeniden bulunamadı.")
            state_changed = True
            continue

        print(f"[pending] {reviewer_name}: {MAX_TEXT_WAIT_ATTEMPTS} denemede de bu yorum bir daha "
              f"bulunamadı (ne Haritalar ne Gmail), elimizdeki bilgiyle metin OLMADAN paylaşılıyor.")
        synthetic_review = {
            "reviewer_name": reviewer_name,
            "rating": rating,
            "review_key": review_key_val,
            "business": business,
            "review_text": "",
            "source": "pending-timeout",
        }
        attempts_this_run += 1
        try:
            _, next_template_index = _post_review_to_instagram(synthetic_review, cfg, _get_ig(), next_template_index)
            newly_processed_review_keys.append(review_key_val)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            # Paylaşım başarısız olursa bekleme listesinde bırak (silme),
            # bir sonraki run'da tekrar denensin (ama deneme sayısı zaten
            # limitte kaldığı için her run'da tekrar denenmeye devam
            # eder - bu kasıtlı, aksi halde o yorum tamamen kaybolurdu).
            print(f"HATA (pending, {reviewer_name}): {exc}", file=sys.stderr)
            pending_reviews[review_key_val] = {**info, "attempts": attempts}
            state_changed = True
            continue

        pending_reviews.pop(review_key_val, None)
        state_changed = True

    if state_changed:
        state["next_template_index"] = next_template_index
        state["processed_message_ids"] = list(processed_message_ids) + newly_processed_message_ids
        state["processed_review_keys"] = list(processed_review_keys) + newly_processed_review_keys
        state["pending_reviews"] = pending_reviews
        state_store.save_and_commit(
            state,
            commit_message=f"state: {processed} yorum işlendi, sıradaki şablon #{next_template_index}",
        )

    print(f"Tamamlandı. {processed} yorum işlendi. Google'a yanıt yazmayı unutma (elle).")


if __name__ == "__main__":
    main()
