"""Regenerate the Fallback Sensors brand icon.

The mark is an ordered stack of sources - the first one active, the others
standing by - and an arrow branching off it and running down to the next
source, which is what the integration does.

Run it from the repository root with Pillow installed:

    python scripts/generate_brand_icon.py

It rewrites custom_components/fallback_sensors/brand/icon.png (256x256) and
icon@2x.png (512x512). Everything is drawn on a supersampled canvas and
downscaled, which is where the antialiasing comes from.
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

S = 2048
U = S / 1024
WHITE = (255, 255, 255, 255)

BAR_X0, BAR_X1, BAR_H = 170, 570, 116
BAR_CENTERS = (300, 512, 724)
BAR_ALPHAS = (255, 150, 92)

ARROW_START_X, ARROW_X, ARROW_W = 600, 800, 50
ARROW_TIP_Y, HEAD_W, HEAD_H = 724, 152, 118


def u(v: float) -> float:
    return v * U


def layer() -> Image.Image:
    return Image.new("RGBA", (S, S), (0, 0, 0, 0))


def build() -> Image.Image:
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, S - 1, S - 1], radius=u(228), fill=255
    )

    column = Image.new("RGB", (1, S))
    for y in range(S):
        t = y / (S - 1)
        column.putpixel(
            (0, y),
            (
                round(0x5B + (0x1E - 0x5B) * t),
                round(0x9B + (0x3F - 0x9B) * t),
                round(0xF8 + (0xA8 - 0xF8) * t),
            ),
        )
    icon = column.resize((S, S), Image.NEAREST).convert("RGBA")
    icon.putalpha(mask)

    for center_y, alpha in zip(BAR_CENTERS, BAR_ALPHAS, strict=True):
        bar = layer()
        ImageDraw.Draw(bar).rounded_rectangle(
            [u(BAR_X0), u(center_y - BAR_H / 2), u(BAR_X1), u(center_y + BAR_H / 2)],
            radius=u(BAR_H / 2),
            fill=(255, 255, 255, alpha),
        )
        icon = Image.alpha_composite(icon, bar)

    arrow = layer()
    draw = ImageDraw.Draw(arrow)
    radius = (ARROW_X - ARROW_START_X) * 0.9
    points = [(u(ARROW_START_X), u(BAR_CENTERS[0]))]
    cx, cy = ARROW_X - radius, BAR_CENTERS[0] + radius
    for i in range(15):
        angle = math.radians(-90 + 90 * i / 14)
        points.append(
            (u(cx + radius * math.cos(angle)), u(cy + radius * math.sin(angle)))
        )
    points.append((u(ARROW_X), u(ARROW_TIP_Y - HEAD_H)))
    draw.line(points, fill=WHITE, width=round(u(ARROW_W)), joint="curve")
    draw.polygon(
        [
            (u(ARROW_X - HEAD_W / 2), u(ARROW_TIP_Y - HEAD_H)),
            (u(ARROW_X + HEAD_W / 2), u(ARROW_TIP_Y - HEAD_H)),
            (u(ARROW_X), u(ARROW_TIP_Y)),
        ],
        fill=WHITE,
    )
    return Image.alpha_composite(icon, arrow)


BRAND_DIR = Path(__file__).resolve().parent.parent / (
    "custom_components/fallback_sensors/brand"
)


def main() -> None:
    """Write the icon at the sizes the brands repository expects."""
    icon = build()
    BRAND_DIR.mkdir(parents=True, exist_ok=True)

    for size, name in ((256, "icon.png"), (512, "icon@2x.png")):
        path = BRAND_DIR / name
        icon.resize((size, size), Image.LANCZOS).save(path)
        print(f"wrote {path} ({size}x{size})")


if __name__ == "__main__":
    main()
