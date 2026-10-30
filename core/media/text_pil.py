"""Text sprites with Pillow (+ libraqm when present) - generalized from a production Hindi/Arabic renderer.

Why Pillow instead of ffmpeg subtitles/drawtext: libass/drawtext builds differ per machine and mis-shape some scripts
(Devanagari, Arabic); Pillow with RAQM (HarfBuzz) shapes them correctly. Everything channel-specific (font file, sizes,
colours, strings) is passed in; nothing is hardcoded here.

    img = render("text", font_path, size_px=48, fill=(255,255,255), outline=3, box=(0,0,0,0.6), maxw=1600, max_lines=2)
"""
from PIL import Image, ImageDraw, ImageFont, features


def raqm_available() -> bool:
    return bool(features.check("raqm"))


def load_font(font_path, size_px: int):
    engine = ImageFont.Layout.RAQM if raqm_available() else ImageFont.Layout.BASIC
    if font_path:
        return ImageFont.truetype(str(font_path), max(1, int(size_px)), layout_engine=engine)
    return ImageFont.load_default(max(1, int(size_px)))  # Pillow >= 10.1: scalable default font


def _wrap(words, font, maxw):
    lines, cur = [], []
    for w in words:
        if cur and maxw and font.getlength(" ".join(cur + [w])) > maxw:
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    return lines + ([cur] if cur else [])


def wrap_balanced(text: str, font, maxw: int, max_lines: int | None = None):
    """Greedy wrap; if exactly two lines result, re-wrap at the narrowest width that still gives two (no one-word orphan)."""
    words = text.split()
    lines = _wrap(words, font, maxw)
    if len(lines) == 2:
        lo, hi = font.getlength(" ".join(words)) / 2, maxw
        for _ in range(12):
            mid = (lo + hi) / 2
            lo, hi = (lo, mid) if len(_wrap(words, font, mid)) <= 2 else (mid, hi)
        lines = _wrap(words, font, hi)
    return [" ".join(l) for l in lines]


def render(text, font_path=None, size_px=48, fill=(255, 255, 255), outline=0, outline_rgb=(0, 0, 0), box=None, radius=0,
           maxw=None, max_lines=None, pitch=1.3, direction=None):
    """-> RGBA PIL image. box=(r,g,b,alpha 0-1) draws ONE rounded box behind all lines. If max_lines is set and the text needs
    more, the size shrinks (down to 70 %) until it fits."""
    scale = 1.0
    while True:
        font = load_font(font_path, size_px * scale)
        lines = wrap_balanced(text, font, maxw) if maxw else [text]
        if not max_lines or len(lines) <= max_lines or scale <= 0.7:
            break
        scale -= 0.05
    px = size_px * scale
    line_h = px * pitch
    widths = [font.getlength(l) for l in lines]
    pad = int(outline + 8)
    W, H = int(max(widths)) + 2 * pad + 2, int(line_h * len(lines)) + 2 * pad
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if box:
        x0 = (W - max(widths)) / 2 - outline
        rect = [x0, pad - outline, x0 + max(widths) + 2 * outline, pad + line_h * len(lines) + outline]
        colour = (*box[:3], int(255 * box[3]))
        d.rounded_rectangle(rect, radius=radius, fill=colour) if radius else d.rectangle(rect, fill=colour)
    for i, (ln, w) in enumerate(zip(lines, widths)):
        kw = dict(font=font, fill=fill, anchor="ls")
        if direction:
            kw["direction"] = direction
        if outline and not box:
            kw.update(stroke_width=int(outline), stroke_fill=outline_rgb)
        d.text(((W - w) / 2, pad + i * line_h + line_h * 0.78), ln, **kw)
    return img
