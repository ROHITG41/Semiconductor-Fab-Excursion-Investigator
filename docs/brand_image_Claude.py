"""brand_image_Claude.py - signs a diagram image with Rohit Kumar's name and handles.

The signature is split between two quiet spots so it never covers the diagram:
  left spot : "Rohit Kumar | linkedin.com/in/ROHITG41"   (left-aligned)
  right spot: "X: @RohitG_AI | All rights reserved"      (right-aligned)
It is drawn as visible text with no background block. Author and copyright are also written into the PNG metadata.

Usage (run on the ORIGINAL, un-signed image; positions are in units of a 1600-pixel-wide diagram):
    python docs/brand_image_Claude.py input.png output.png [left_x left_y right_x right_y]
Defaults suit docs/architecture_Claude.png: 40 122 1560 778
"""
from __future__ import annotations

import sys

from PIL import Image, ImageDraw, ImageFont
from PIL.PngImagePlugin import PngInfo

NAME = "Rohit Kumar"
LINKEDIN = "linkedin.com/in/ROHITG41"
X_HANDLE = "@RohitG_AI"
RIGHTS = "All rights reserved"
LEFT_TEXT = f"{NAME}  |  LinkedIn: {LINKEDIN}"
RIGHT_TEXT = f"X: {X_HANDLE}  |  {RIGHTS}"
INK = (51, 65, 85, 215)          # slate, slightly soft so it reads as a signature, not as content


def _font(size: int):
    for n in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def brand(src: str, dst: str, left=(40, 122), right=(1560, 778)) -> None:
    img = Image.open(src).convert("RGBA")
    w, h = img.size
    u = w / 1600.0
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = _font(int(15 * u))
    d.text((left[0] * u, left[1] * u), LEFT_TEXT, font=f, fill=INK, anchor="ls")
    d.text((right[0] * u, right[1] * u), RIGHT_TEXT, font=f, fill=INK, anchor="rs")
    out = Image.alpha_composite(img, layer).convert("RGB")
    meta = PngInfo()
    meta.add_text("Author", NAME)
    meta.add_text("Copyright", f"Copyright (c) 2026 {NAME}. {RIGHTS}.")
    meta.add_text("Source", f"{LINKEDIN} | X {X_HANDLE} | github.com/ROHITG41")
    out.save(dst, pnginfo=meta)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) not in (2, 6):
        sys.exit("usage: python docs/brand_image_Claude.py input.png output.png [left_x left_y right_x right_y]")
    pos = {}
    if len(a) == 6:
        pos = dict(left=(float(a[2]), float(a[3])), right=(float(a[4]), float(a[5])))
    brand(a[0], a[1], **pos)
    print("written", a[1])
