"""
Google Business Profile'ın gönderdiği "X, İşletme için yorum yaptı" bildirim
mailini Gmail'den (IMAP + Uygulama Şifresi ile, Google Cloud/API/kart
GEREKTİRMEDEN) okuyup içinden yorumu yapan kişinin adını ve yıldız puanını
çıkarır.

Google Business Profile API'nin aksine bu yöntemin bir onay süreci yok,
ücretsiz ve limitsiz (Gmail'in kendi normal kullanım sınırları içinde -
ayda birkaç yüz mail bu sınırların çok altında).

DEZAVANTAJ: bu yöntemle Google yorumuna OTOMATİK yanıt yazamıyoruz (o hâlâ
kısıtlı API'yi gerektiriyor) - o kısmı elle yapman gerekiyor, tıpkı şu ana
kadar yaptığın gibi.

Bir Gmail hesabı birden fazla işletmeyi yönetiyorsa (senin durumun gibi),
Config.REVIEW_SOURCE_BUSINESS_NAME ile hangi işletmenin yorumlarının
işleneceğini filtreliyoruz - yoksa hepsi aynı Instagram hesabına düşer.
"""

import email
import imaplib
import re
from datetime import datetime, timedelta
from email.header import decode_header

from automation import review_key

SENDER = "businessprofile-noreply@google.com"

# Örnek konu satırı: "Hasan, Niğde Gezi Otobüsü için yorum yaptı"
SUBJECT_RE = re.compile(r"^(?P<name>[^,]+),\s*(?P<business>.+?)\s+için yorum yaptı\s*$")

# Örnek gövde cümlesi: "Tebrikler! 5 yıldızlı yeni bir yorumunuz var"
RATING_RE = re.compile(r"(\d+)\s*yıldızlı yeni bir yorumunuz var")

# IMAP SEARCH'ün taramayacağı kadar eskiye gitmemek için pencere (gün)
SEARCH_WINDOW_DAYS = 4


def _decode(value) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _get_plain_text(msg) -> str:
    """Mailin gövdesini düz metne çevirir (text/plain varsa onu, yoksa
    text/html'i etiketlerinden temizleyerek kullanır)."""
    plain, html = None, None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain" and plain is None:
                plain = part.get_payload(decode=True)
            elif ctype == "text/html" and html is None:
                html = part.get_payload(decode=True)
    else:
        if msg.get_content_type() == "text/plain":
            plain = msg.get_payload(decode=True)
        else:
            html = msg.get_payload(decode=True)

    if plain:
        return plain.decode(msg.get_content_charset() or "utf-8", errors="replace")
    if html:
        text = html.decode(msg.get_content_charset() or "utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", text)  # etiketleri sil
        text = re.sub(r"\s+", " ", text)
        return text
    return ""


def fetch_new_reviews(gmail_address: str, app_password: str, already_processed: set, business_filter: str = ""):
    """
    Dönüş: [{"message_id": ..., "reviewer_name": ..., "rating": int, "business": ...}, ...]
    already_processed: state.json'daki processed_message_ids seti - bunlar atlanır.
    business_filter: doluysa, konu satırındaki işletme adı bunu İÇERMEYEN mailler atlanır.
    """
    results = []

    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        imap.login(gmail_address, app_password)
        imap.select("INBOX")

        since_date = (datetime.utcnow() - timedelta(days=SEARCH_WINDOW_DAYS)).strftime("%d-%b-%Y")
        status, data = imap.search(None, f'(FROM "{SENDER}" SINCE {since_date})')
        if status != "OK":
            return results

        uids = data[0].split()
        for uid in uids:
            status, msg_data = imap.fetch(uid, "(RFC822)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                continue

            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            message_id = msg.get("Message-ID", "").strip()
            if not message_id or message_id in already_processed:
                continue

            subject = _decode(msg.get("Subject", ""))
            m = SUBJECT_RE.match(subject.strip())
            if not m:
                continue  # bu bizim aradığımız "yeni yorum" maili değil

            reviewer_name = m.group("name").strip()
            business_name = m.group("business").strip()

            if business_filter and business_filter.lower() not in business_name.lower():
                continue

            body = _get_plain_text(msg)
            rating_match = RATING_RE.search(body)
            rating = int(rating_match.group(1)) if rating_match else 0

            results.append({
                "source": "gmail",
                "message_id": message_id,
                "reviewer_name": reviewer_name,
                "rating": rating,
                # Google'ın bildirim maili genelde yorumun tam metnini
                # içermiyor (sadece "X yıldızlı yeni bir yorumunuz var"
                # cümlesi) - bu yüzden burada boş bırakılıyor. Yorum metni
                # asıl olarak maps_watch.py (Google Haritalar taraması)
                # üzerinden geliyor.
                "review_text": "",
                "business": business_name,
                "review_key": review_key.make_key(reviewer_name, rating, business_name),
            })
    finally:
        try:
            imap.close()
        except Exception:
            pass
        imap.logout()

    return results
