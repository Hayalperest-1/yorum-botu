"""
Hazır şablon GÖRSELİNİN (jpg/png) üzerine yorumcunun adını, yıldız
puanını, yorum metnini ve bir teşekkür mesajını otomatik olarak yazan
modül. Sonucu yeni bir dosyaya (assets/generated/ altına) kaydeder -
orijinal şablon dosyaları DEĞİŞTİRİLMEZ, her paylaşım için üzerine yazı
eklenmiş yeni bir kopya üretilir.

NOT: Sadece GÖRSEL şablonlar için çalışır. Video şablonlar (.mp4) için
metni videonun üzerine "yakmak" çok daha karmaşık bir işlem (ffmpeg/
moviepy gerektirir) olduğu için bu adım atlanıyor - video şablonlar
olduğu gibi (yazısız) paylaşılmaya devam ediyor. main.py bu ayrımı
template["type"] alanına bakarak zaten yapıyor.
"""

import os

from PIL import Image, ImageDraw, ImageFont

# Ubuntu (GitHub Actions runner'ı) üzerinde genelde hazır bulunan, Türkçe
# karakterleri (ç, ğ, ı, ö, ş, ü) doğru gösteren font dosyaları - sırayla
# denenir, hiçbiri yoksa Pillow'un temel (Türkçe karakterleri düzgün
# göstermeyebilecek) varsayılan fontuna düşülür.
FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]


def _load_font(candidates, size):
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(draw, text, font, max_width):
    if not text:
        return []
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_story_image(
    template_path: str,
    reviewer_name: str,
    rating: int,
    review_text: str,
    thank_you_text: str,
    output_path: str,
    max_review_chars: int = 220,
) -> str:
    img = Image.open(template_path).convert("RGBA")
    width, height = img.size

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    name_font = _load_font(FONT_CANDIDATES_BOLD, max(26, width // 19))
    stars_font = _load_font(FONT_CANDIDATES_BOLD, max(28, width // 17))
    body_font = _load_font(FONT_CANDIDATES_REGULAR, max(18, width // 29))
    thanks_font = _load_font(FONT_CANDIDATES_BOLD, max(20, width // 24))

    safe_rating = max(0, min(5, int(rating or 0)))
    stars = ("★" * safe_rating) + ("☆" * (5 - safe_rating))

    text = (review_text or "").strip()
    if len(text) > max_review_chars:
        text = text[: max_review_chars - 1].rstrip() + "…"

    padding = int(width * 0.09)
    text_max_width = width - 2 * padding

    lines = []  # (kind, text, font)
    if reviewer_name:
        lines.append(("name", reviewer_name.strip(), name_font))
    lines.append(("stars", stars, stars_font))
    if text:
        for wl in _wrap_text(draw, f"“{text}”", body_font, text_max_width):
            lines.append(("body", wl, body_font))
    if thank_you_text:
        for wl in _wrap_text(draw, thank_you_text.strip(), thanks_font, text_max_width):
            lines.append(("thanks", wl, thanks_font))

    if not lines:
        # Yazacak hiçbir şey yoksa (isim de yoksa) şablonu olduğu gibi
        # kaydet - en azından çökmesin.
        img.convert("RGB").save(output_path, quality=92)
        return output_path

    line_gap = max(4, int(height * 0.012))
    heights = []
    for _, txt, font in lines:
        bbox = draw.textbbox((0, 0), txt, font=font)
        heights.append(bbox[3] - bbox[1])

    section_gap = int(height * 0.02)
    total_text_height = sum(heights) + line_gap * (len(lines) - 1)
    # İsim/yıldız ile yorum metni, yorum metni ile teşekkür arasına biraz
    # daha fazla boşluk bırak (sadece satır arası değil, "bölüm" arası).
    kinds = [k for k, _, _ in lines]
    if "body" in kinds and "stars" in kinds:
        total_text_height += section_gap
    if "thanks" in kinds and ("body" in kinds or "stars" in kinds):
        total_text_height += section_gap

    box_padding_y = int(height * 0.045)
    box_height = min(total_text_height + 2 * box_padding_y, int(height * 0.7))
    box_top = (height - box_height) // 2
    box_bottom = box_top + box_height

    draw.rounded_rectangle(
        [padding // 2, box_top, width - padding // 2, box_bottom],
        radius=int(width * 0.05),
        fill=(0, 0, 0, 155),
    )

    y = box_top + box_padding_y
    prev_kind = None
    for (kind, txt, font), h in zip(lines, heights):
        if prev_kind == "stars" and kind == "body":
            y += section_gap
        if prev_kind in ("body", "stars") and kind == "thanks":
            y += section_gap

        bbox = draw.textbbox((0, 0), txt, font=font)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        if kind == "stars":
            fill = (255, 205, 40, 255)
        else:
            fill = (255, 255, 255, 255)
        draw.text((x, y), txt, font=font, fill=fill)
        y += h + line_gap
        prev_kind = kind

    combined = Image.alpha_composite(img, overlay).convert("RGB")
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    combined.save(output_path, quality=92)
    return output_path
