"""
Aynı yorumu iki farklı kaynaktan (Gmail bildirimi + Google Haritalar taraması)
yakalayıp İKİ KERE paylaşmamak için, her yoruma kaynaktan bağımsız, içeriğe
dayalı bir "kimlik" (review_key) üretiyoruz. İki kaynak da aynı yorum için
aynı review_key'i üretirse, state.json'daki processed_review_keys sayesinde
ikincisi otomatik atlanır.
"""

import hashlib


def make_key(reviewer_name: str, rating: int, business: str) -> str:
    normalized = f"{(reviewer_name or '').strip().lower()}|{rating}|{(business or '').strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
