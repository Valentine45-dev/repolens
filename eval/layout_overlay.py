"""Overlay and difference images from eval/layout_shift.mjs: for each route the skeleton (what
index.html shows before the app runs) is laid over the loaded page. Where the placeholders sit on
the elements they stand for, the two line up; where they do not, the outlines double.

    python eval/layout_overlay.py DIR LABEL
"""

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

directory, label = Path(sys.argv[1]), sys.argv[2]
for route in ("home", "explore", "findings"):
    skeleton = directory / f"{label}-{route}-skeleton.png"
    loaded = directory / f"{label}-{route}-loaded.png"
    if not (skeleton.exists() and loaded.exists()):
        continue
    a, b = Image.open(skeleton).convert("RGB"), Image.open(loaded).convert("RGB")
    # Overlay: skeleton in red, loaded in cyan, on white. Dark where both have ink.
    red = ImageChops.multiply(a, Image.new("RGB", a.size, (255, 90, 90)))
    cyan = ImageChops.multiply(b, Image.new("RGB", b.size, (90, 200, 255)))
    overlay = ImageChops.multiply(red, cyan)
    draw = ImageDraw.Draw(overlay)
    draw.rectangle([0, 0, 330, 20], fill=(255, 255, 255))
    draw.text((6, 4), f"{label} {route}: red = skeleton, cyan = loaded", fill=(0, 0, 0))
    overlay.save(directory / f"{label}-{route}-overlay.png")
    diff = ImageChops.difference(a, b).point(lambda v: 255 if v > 24 else 0).convert("L")
    changed = sum(1 for v in diff.getdata() if v) / (diff.width * diff.height) * 100
    print(f"{label} {route}: {changed:.1f}% of pixels differ (text and counts differ by design)")
