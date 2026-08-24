"""
Ana akış - bu dosya her tetiklendiğinde (15 dakikada bir, GitHub Actions
üzerinden) çalışır:

  1) Gmail'den, Google'ın gönderdiği "X, İşletme için yorum yaptı" bildirim
     maillerini tara; daha önce işlenmemiş (state.json'da olmayan) olanları
     bul -> bunlar YENİ yorumlardır
  2) Puanı yeterince yüksekse (varsayılan 4+): assets/story-templates/
     klasöründeki hazır görsel/video havuzundan SIRADAKİ dosyayı al,
     Instagram hikayesine olduğu gibi paylaş, sırayı bir ilerlet
  3) İşlenen her yorumun mail ID'sini state.json'a ekle (bir daha "yeni"
     sayılmasın diye) ve tek seferde depoya kaydet

NOT: Bu akış Google'a OTOMATİK yanıt yazmıyor (Business Profile API'nin
kısıtlı/onaylı erişimi olmadan bu mümkün değil) - yorumu Google üzerinden
yanıtlamak hâlâ elle yapman gereken bir adım.
"""

import sys

from dotenv import load_dotenv

# Yerelde ".env" dosyası varsa ortam değişkenlerini oradan yükler
# (GitHub Actions'ta .env dosyası olmadığı için burası hiçbir şey yapmaz,
# secrets zaten ortam değişkeni olarak geliyor). Config'i içeri
# aktarmadan ÖNCE çalışması şart, çünkü Config değerleri import anında
# okuyor.
load_dotenv()

from automation.config import Config
from automation.instagram import InstagramClient
from automation import template_queue
from automation import state_store
from automation import gmail_watch
from automation.git_publish import raw_url_for


def main():
    cfg = Config

    state = state_store.load()
    already_processed = set(state.get("processed_message_ids", []))

    reviews = gmail_watch.fetch_new_reviews(
        gmail_address=cfg.GMAIL_ADDRESS,
        app_password=cfg.GMAIL_APP_PASSWORD,
        already_processed=already_processed,
        business_filter=cfg.REVIEW_SOURCE_BUSINESS_NAME,
    )

    if not reviews:
        print("Yeni yorum yok, çıkılıyor.")
        return

    print(f"{len(reviews)} yeni yorum bulundu, en fazla {cfg.MAX_REVIEWS_PER_RUN} tanesi işlenecek.")

    ig = InstagramClient(
        access_token=cfg.IG_ACCESS_TOKEN,
        ig_user_id=cfg.IG_USER_ID,
        api_version=cfg.GRAPH_API_VERSION,
    )

    next_template_index = state.get("next_template_index", 0)
    newly_processed_ids = []
    processed = 0
    state_changed = False

    for review in reviews:
        if processed >= cfg.MAX_REVIEWS_PER_RUN:
            print("Bu çalıştırma için işlem limiti doldu, kalanlar bir sonraki çalıştırmada işlenecek.")
            break

        reviewer_name = review["reviewer_name"]
        rating = review["rating"]

        print(f"İşleniyor: {reviewer_name} - {rating} yıldız ({review['business']})")

        try:
            if rating >= cfg.MIN_RATING_TO_POST:
                template = template_queue.get_template_at(next_template_index)
                media_url = raw_url_for(template["path"], cfg.GITHUB_REPOSITORY)

                print(f"Sıradaki şablon: {template['filename']} ({template['index'] + 1}/{template['total']})")

                media_id = ig.post_story(media_url, is_video=(template["type"] == "video"))
                print(f"Instagram hikayesine paylaşıldı: {media_id}")

                next_template_index = template["index"] + 1
            else:
                print(f"Puan {rating}, {cfg.MIN_RATING_TO_POST} altında (ya da okunamadı) -> hikayeye paylaşılmadı.")

            newly_processed_ids.append(review["message_id"])
            state_changed = True
            processed += 1

        except Exception as exc:  # noqa: BLE001
            # Bir yorumda hata olsa bile diğerlerini işlemeye devam et;
            # bu yorumu "işlendi" olarak işaretlemediğimiz için bir
            # sonraki çalıştırmada tekrar denenecek.
            print(f"HATA ({reviewer_name}): {exc}", file=sys.stderr)

    if state_changed:
        state["next_template_index"] = next_template_index
        state["processed_message_ids"] = list(already_processed) + newly_processed_ids
        state_store.save_and_commit(
            state,
            commit_message=f"state: {processed} yorum işlendi, sıradaki şablon #{next_template_index}",
        )

    print(f"Tamamlandı. {processed} yorum işlendi. Google'a yanıt yazmayı unutma (elle).")


if __name__ == "__main__":
    main()
