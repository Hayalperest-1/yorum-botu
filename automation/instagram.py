"""
Instagram Graph API üzerinden hikayeye (Story) görsel VEYA video paylaşan
istemci.

Şartlar:
- Instagram hesabı Business veya Creator (profesyonel) hesap olmalı
- Bir Facebook Sayfasına bağlı olmalı
- Uzun ömürlü (long-lived) bir access token gerekiyor (README'de anlatılıyor)

Instagram, paylaşılacak medyayı KENDİSİ indirir - yani verdiğimiz URL
herkese açık, internetten erişilebilir bir adres olmalı. Bu projede bu
adresi git_publish.py, deponun içindeki dosyayı kullanarak üretiyor.

Video için Instagram'ın beklentileri: MP4, H.264 video / AAC ses, dikey
(9:16) format, hikaye için en fazla ~60 saniye. Video işlenmesi görsele
göre daha uzun sürebildiği için bekleme süresi daha uzun tutuluyor.
"""

import time
import requests


class InstagramClient:
    def __init__(self, access_token: str, ig_user_id: str, api_version: str = "v21.0"):
        self.access_token = access_token
        self.ig_user_id = ig_user_id
        self.base = f"https://graph.facebook.com/{api_version}"

    def post_story(self, media_url: str, is_video: bool = False, max_wait_seconds: int = None) -> str:
        """
        1) media_url'den bir 'media container' oluşturur
        2) container hazır olana kadar bekler
        3) container'ı hikaye olarak yayınlar
        Dönüş: yayınlanan medyanın id'si
        """
        if max_wait_seconds is None:
            max_wait_seconds = 180 if is_video else 60

        container_id = self._create_container(media_url, is_video)
        self._wait_until_ready(container_id, max_wait_seconds)
        return self._publish(container_id)

    def _create_container(self, media_url: str, is_video: bool) -> str:
        data = {
            "media_type": "STORIES",
            "access_token": self.access_token,
        }
        if is_video:
            data["video_url"] = media_url
        else:
            data["image_url"] = media_url

        resp = requests.post(f"{self.base}/{self.ig_user_id}/media", data=data, timeout=30)
        if not resp.ok:
            raise RuntimeError(f"Instagram medya oluşturma hatası ({resp.status_code}): {resp.text}")
        return resp.json()["id"]

    def _wait_until_ready(self, container_id: str, max_wait_seconds: int) -> None:
        deadline = time.time() + max_wait_seconds
        while time.time() < deadline:
            resp = requests.get(
                f"{self.base}/{container_id}",
                params={"fields": "status_code", "access_token": self.access_token},
                timeout=30,
            )
            if not resp.ok:
                raise RuntimeError(f"Instagram durum sorgusu hatası ({resp.status_code}): {resp.text}")
            status = resp.json().get("status_code")
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise RuntimeError(f"Instagram medya işleme hatası: container {container_id}")
            time.sleep(5)
        raise TimeoutError(f"Instagram medya container {max_wait_seconds} sn içinde hazır olmadı.")

    def _publish(self, container_id: str) -> str:
        resp = requests.post(
            f"{self.base}/{self.ig_user_id}/media_publish",
            data={"creation_id": container_id, "access_token": self.access_token},
            timeout=30,
        )
        if not resp.ok:
            raise RuntimeError(f"Instagram yayınlama hatası ({resp.status_code}): {resp.text}")
        return resp.json()["id"]
