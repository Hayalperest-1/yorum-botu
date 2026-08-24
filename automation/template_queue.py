"""
Sabit bir görsel/video havuzunu SIRAYLA döndürür: 1. yorumda 1. şablon,
2. yorumda 2. şablon, ... havuz biterse başa sarar.

Şablonlar `assets/story-templates/` klasöründe duruyor. Sırayı dosya adına
göre belirliyoruz - bu yüzden dosyaları `01.jpg`, `02.jpg`, ... `12.mp4`
gibi İKİ HANELİ numarayla adlandır (numara olmadan alfabetik sıralama
"10.jpg"yi "2.jpg"den önce koyar, karışıklık olur).

Hangi şablonun sırada olduğu, state_store üzerinden (automation/state.json)
tutuluyor.
"""

import os

TEMPLATES_DIR = "assets/story-templates"

VIDEO_EXT = {".mp4", ".mov"}
IMAGE_EXT = {".jpg", ".jpeg", ".png"}


def list_templates() -> list:
    if not os.path.isdir(TEMPLATES_DIR):
        raise RuntimeError(f"{TEMPLATES_DIR} klasörü yok.")
    files = sorted(
        f
        for f in os.listdir(TEMPLATES_DIR)
        if os.path.splitext(f)[1].lower() in VIDEO_EXT | IMAGE_EXT
    )
    if not files:
        raise RuntimeError(f"{TEMPLATES_DIR} klasöründe hiç şablon görsel/video yok.")
    return files


def get_template_at(index: int) -> dict:
    files = list_templates()
    idx = index % len(files)
    filename = files[idx]
    ext = os.path.splitext(filename)[1].lower()
    media_type = "video" if ext in VIDEO_EXT else "image"
    return {
        "filename": filename,
        "path": f"{TEMPLATES_DIR}/{filename}",
        "type": media_type,
        "index": idx,
        "total": len(files),
    }
