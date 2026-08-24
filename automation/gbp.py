"""
KULLANILMIYOR - main.py artık yorumları Gmail bildirim maillerinden
(automation/gmail_watch.py) okuyor, bu dosyayı çağırmıyor.

Bu dosya Google Business Profile API'nin (My Business API v4) kısıtlı/onaylı
erişimini gerektiriyordu - o onay süreci çok yavaş/belirsiz olduğu için bu
yoldan vazgeçildi. İleride bir gün o erişim onaylanırsa, "yoruma otomatik
Google yanıtı yazma" özelliğini eklemek için burası bir başlangıç noktası
olabilir (reply_to_review fonksiyonuna bak) - şu an devrede değil.
"""

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://mybusiness.googleapis.com/v4"


class GBPClient:
    def __init__(self, client_id, client_secret, refresh_token, account_id, location_id):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.account_id = account_id
        self.location_id = location_id
        self._access_token = None

    def _refresh_access_token(self) -> str:
        resp = requests.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        resp.raise_for_status()
        self._access_token = resp.json()["access_token"]
        return self._access_token

    def _headers(self):
        if not self._access_token:
            self._refresh_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    def list_reviews(self) -> list:
        """Konumun tüm yorumlarını döndürür (Google'ın verdiği sırayla)."""
        url = f"{API_BASE}/accounts/{self.account_id}/locations/{self.location_id}/reviews"
        reviews = []
        page_token = None
        while True:
            params = {"pageToken": page_token} if page_token else {}
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            if resp.status_code == 401:
                # token süresi dolmuş olabilir, bir kere yenile ve tekrar dene
                self._refresh_access_token()
                resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            reviews.extend(data.get("reviews", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return reviews

    def reply_to_review(self, review_name: str, comment: str) -> None:
        """
        review_name: review objesinin "name" alanı, örn.
        "accounts/123/locations/456/reviews/AbCdEf"
        """
        url = f"{API_BASE}/{review_name}/reply"
        resp = requests.put(
            url, headers=self._headers(), json={"comment": comment}, timeout=30
        )
        resp.raise_for_status()


def star_rating_to_int(star_rating: str) -> int:
    """Google 'ONE'..'FIVE' string döndürür, sayıya çeviririz."""
    mapping = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}
    return mapping.get(star_rating, 0)
