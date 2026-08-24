"""
İSTEĞE BAĞLI MODÜL - varsayılan akış (main.py) bunu kullanmıyor; hazır
şablon havuzunu (assets/story-templates/) olduğu gibi paylaşıyor. Eğer
ileride yorumu yapan kişinin adını görselin ÜZERİNE otomatik yazdırmak
istersen bu modülü main.py içinde template_queue'nun yerine/yanında
çağırabilirsin.

1080x1920 (Instagram hikaye boyutu) teşekkür görseli üretir.
Tasarım, size gösterdiğim "Yön 1 - Sıcak & Zarif" örneğiyle aynı ruhta:
krem zemin, üstte logo dairesi, ortada yıldızlar + başlık + alt metin,
altta işletme adı.

Yazı tipleri: assets/fonts/ klasörüne indirdiğin iki Google Font
kullanılıyor (README'de indirme linkleri var):
  - InstrumentSerif-Regular.ttf  (başlık)
  - Manrope-Bold.ttf / Manrope-Medium.ttf (küçük yazılar)
Fontlar yoksa Pillow'un varsayılan fontuna düşer (çirkin ama çalışır).
"""

import os
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1920
BG_COLOR = (250, 246, 239)
TEXT_DARK = (58, 46, 38)
TEXT_MUTED = (117, 104, 92)

FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")


def _load_font(filename: str, size: int) -> ImageFont.FreeTypeFont:
    path = os.path.join(FONTS_DIR, filename)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _hex_to_rgb(hex_color: str):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _draw_star(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color):
    import math

    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        radius = r if i % 2 == 0 else r * 0.42
        x = cx + radius * math.cos(angle)
        y = cy - radius * math.sin(angle)
        points.append((x, y))
    draw.polygon(points, fill=color)


def _wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_thankyou_image(
    reviewer_name: str,
    rating: int,
    business_name: str,
    subtext: str,
    accent_hex: str,
    logo_path: str,
    out_path: str,
) -> str:
    accent = _hex_to_rgb(accent_hex)
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # --- logo dairesi (üst) ---
    logo_r = 88
    logo_cx, logo_cy = WIDTH // 2, 230
    if logo_path and os.path.exists(logo_path):
        logo_img = Image.open(logo_path).convert("RGBA").resize((logo_r * 2, logo_r * 2))
        mask = Image.new("L", (logo_r * 2, logo_r * 2), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, logo_r * 2, logo_r * 2), fill=255)
        img.paste(logo_img, (logo_cx - logo_r, logo_cy - logo_r), mask)
    else:
        draw.ellipse(
            (logo_cx - logo_r, logo_cy - logo_r, logo_cx + logo_r, logo_cy + logo_r),
            outline=(150, 138, 126),
            width=3,
        )
        small_font = _load_font("Manrope-Bold.ttf", 22)
        w = draw.textlength("LOGO", font=small_font)
        draw.text((logo_cx - w / 2, logo_cy - 12), "LOGO", font=small_font, fill=(140, 128, 116))

    # --- yıldızlar ---
    star_y = 520
    star_r = 26
    gap = 74
    start_x = WIDTH // 2 - gap * 2
    for i in range(rating):
        _draw_star(draw, start_x + i * gap, star_y, star_r, accent)

    # --- başlık ---
    headline_font = _load_font("InstrumentSerif-Regular.ttf", 96)
    headline = f"Teşekkürler,"
    headline2 = f"{reviewer_name}!"
    y = 650
    for line in (headline, headline2):
        w = draw.textlength(line, font=headline_font)
        draw.text((WIDTH / 2 - w / 2, y), line, font=headline_font, fill=TEXT_DARK)
        y += 118

    # --- alt metin ---
    body_font = _load_font("Manrope-Medium.ttf", 32)
    lines = _wrap_text(draw, subtext, body_font, max_width=760)
    y += 40
    for line in lines:
        w = draw.textlength(line, font=body_font)
        draw.text((WIDTH / 2 - w / 2, y), line, font=body_font, fill=TEXT_MUTED)
        y += 46

    # --- alt: işletme adı ---
    rule_y = HEIGHT - 260
    draw.line((WIDTH / 2 - 60, rule_y, WIDTH / 2 + 60, rule_y), fill=accent, width=2)

    name_font = _load_font("InstrumentSerif-Regular.ttf", 40)
    w = draw.textlength(business_name, font=name_font)
    draw.text((WIDTH / 2 - w / 2, rule_y + 30), business_name, font=name_font, fill=TEXT_DARK)

    tag_font = _load_font("Manrope-Bold.ttf", 20)
    tag = "GOOGLE YORUMLARI"
    w = draw.textlength(tag, font=tag_font)
    draw.text((WIDTH / 2 - w / 2, rule_y + 90), tag, font=tag_font, fill=TEXT_MUTED)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "JPEG", quality=92)
    return out_path
