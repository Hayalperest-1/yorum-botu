"""
Botun "hafızası" — GitHub Actions'ın her çalıştırması hafızasız (fresh)
başladığı için, iki şeyi depodaki küçük bir JSON dosyasında saklıyoruz:

  - next_template_index: assets/story-templates/ havuzunda sırada hangi
    dosyanın olduğu
  - processed_message_ids: hangi Gmail yorumu bildirim maillerinin zaten
    işlendiği (aynı yorumu iki kere paylaşmamak için)

Bu dosya her çalıştırmanın SONUNDA bir kez okunup güncellenip commit'leniyor.
"""

import json
import os

from automation.git_publish import commit_and_push

STATE_FILE = "automation/state.json"

DEFAULT_STATE = {
    "next_template_index": 0,
    "processed_message_ids": [],
    "processed_review_keys": [],
}

# processed_message_ids / processed_review_keys listeleri sınırsız büyümesin
# diye son N tanesini tutuyoruz
MAX_PROCESSED_IDS = 1000


def load() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            data = json.load(f)
        merged = dict(DEFAULT_STATE)
        merged.update(data)
        return merged
    return dict(DEFAULT_STATE)


def save_and_commit(state: dict, commit_message: str) -> None:
    # listeleri sınırlı tut
    ids = state.get("processed_message_ids", [])
    if len(ids) > MAX_PROCESSED_IDS:
        state["processed_message_ids"] = ids[-MAX_PROCESSED_IDS:]

    keys = state.get("processed_review_keys", [])
    if len(keys) > MAX_PROCESSED_IDS:
        state["processed_review_keys"] = keys[-MAX_PROCESSED_IDS:]

    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    commit_and_push([STATE_FILE], commit_message)
