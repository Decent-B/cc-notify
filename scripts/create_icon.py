"""
Generate assets/icon.ico from scratch using Pillow.

Run once before building with PyInstaller, or as part of the CI workflow:
    python scripts/create_icon.py

Produces a multi-resolution .ico containing 16, 32, 48, 64, 128, and 256 px
variants so Windows can pick the best size for each display context (taskbar,
tray, file explorer, etc.).
"""
from __future__ import annotations

from pathlib import Path


def _draw_bell(size: int):
    """Return a single-size RGBA PIL Image with the cc-notify bell icon."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = max(1, size // 16)

    # Purple background circle (Anthropic brand-ish purple)
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=(134, 94, 212, 255),
    )

    # Scale bell proportions relative to canvas size.
    cx = size // 2
    bw = int(size * 0.38)    # bell width
    bh = int(size * 0.30)    # bell body height
    top = int(size * 0.22)   # top of bell arch

    # Bell arch (filled semicircle) — drawn first so body overlaps it cleanly.
    draw.pieslice(
        [cx - bw // 2, top, cx + bw // 2, top + bh],
        start=180,
        end=0,
        fill=(255, 255, 255, 230),
    )

    # Bell body (rounded rectangle below arch midpoint).
    body_top = top + bh // 2
    body_bot = int(size * 0.65)
    r = max(1, size // 12)
    draw.rounded_rectangle(
        [cx - bw // 2, body_top, cx + bw // 2, body_bot],
        radius=r,
        fill=(255, 255, 255, 230),
    )

    # Clapper dot below the body.
    cr = max(1, size // 14)
    draw.ellipse(
        [cx - cr, body_bot, cx + cr, body_bot + cr * 2],
        fill=(255, 255, 255, 230),
    )

    # Stem at top centre (only meaningful at larger sizes).
    if size >= 32:
        sw = max(2, size // 14)
        sh = max(3, size // 12)
        draw.rectangle(
            [cx - sw // 2, top - sh, cx + sw // 2, top],
            fill=(255, 255, 255, 200),
        )

    return img


def main() -> None:
    out = Path(__file__).parent.parent / "assets" / "icon.ico"
    out.parent.mkdir(parents=True, exist_ok=True)

    # Draw at maximum resolution, then let Pillow resize for each ICO slot.
    # This is the correct Pillow API for multi-resolution ICO files.
    base = _draw_bell(256)

    target_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    base.save(out, format="ICO", sizes=target_sizes)

    print(f"Icon written to {out}  ({out.stat().st_size:,} bytes, {len(target_sizes)} resolutions)")


if __name__ == "__main__":
    main()
