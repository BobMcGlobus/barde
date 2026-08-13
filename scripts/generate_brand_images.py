#!/usr/bin/env python3
"""Generate the brand images in ``custom_components/barde/brand``.

Since Home Assistant 2026.3 custom integrations ship their own brand assets;
the brands repository no longer accepts pull requests for them. Everything is
drawn here so the images can be regenerated instead of being binary blobs
nobody can touch.

    pip install pillow
    python scripts/generate_brand_images.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "custom_components" / "barde" / "brand"

# Drawn oversized, then downsampled — cheap anti-aliasing.
SUPERSAMPLE = 4

WHITE = (255, 255, 255, 255)
STRING_WHITE = (255, 255, 255, 170)
INDIGO = (49, 46, 129, 255)
VIOLET = (124, 58, 237, 255)
VIOLET_LIGHT = (167, 139, 250, 255)
FUCHSIA = (192, 132, 252, 255)
INK = (60, 30, 120, 255)

FONT_CANDIDATES = (
    "C:/Windows/Fonts/seguisb.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)

# The lyre, in a 1024x1024 design space. Left half only — the right arm is
# mirrored so the shape stays symmetric.
ARM_LEFT = ((406, 726), (336, 566), (232, 468), (208, 250))
YOKE = (160, 212, 864, 270)
BODY = (386, 690, 638, 862)
STRINGS_Y = (270, 700)
STRINGS_X = (404, 620)
STRING_COUNT = 6
DESIGN = 1024


def cubic(
    points: tuple[tuple[int, int], ...], steps: int = 80
) -> list[tuple[float, float]]:
    """Sample a cubic Bézier curve."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
    curve = []
    for step in range(steps + 1):
        t = step / steps
        u = 1 - t
        a, b, c, d = u**3, 3 * u**2 * t, 3 * u * t**2, t**3
        curve.append(
            (
                a * x0 + b * x1 + c * x2 + d * x3,
                a * y0 + b * y1 + c * y2 + d * y3,
            )
        )
    return curve


def draw_lyre(
    draw: ImageDraw.ImageDraw,
    left: float,
    top: float,
    size: float,
    color: tuple[int, int, int, int],
    strings: tuple[int, int, int, int],
) -> None:
    """Draw the lyre into a square box of ``size`` pixels at (left, top)."""
    scale = size / DESIGN

    def point(x: float, y: float) -> tuple[float, float]:
        return (left + x * scale, top + y * scale)

    stroke = max(2, round(34 * scale))

    # Sound box, then the two arms growing out of it.
    x0, y0, x1, y1 = BODY
    draw.rounded_rectangle(
        [point(x0, y0), point(x1, y1)], radius=60 * scale, fill=color
    )
    for mirror in (False, True):
        arm = [point(DESIGN - x if mirror else x, y) for x, y in cubic(ARM_LEFT)]
        draw.line(arm, fill=color, width=stroke, joint="curve")
        draw.ellipse(
            [
                (arm[-1][0] - stroke / 2, arm[-1][1] - stroke / 2),
                (arm[-1][0] + stroke / 2, arm[-1][1] + stroke / 2),
            ],
            fill=color,
        )

    # Yoke across the arm tips.
    x0, y0, x1, y1 = YOKE
    draw.rounded_rectangle(
        [point(x0, y0), point(x1, y1)], radius=26 * scale, fill=color
    )

    # Strings.
    string_width = max(1, round(12 * scale))
    top_y, bottom_y = STRINGS_Y
    first, last = STRINGS_X
    for index in range(STRING_COUNT):
        x = first + (last - first) * index / (STRING_COUNT - 1)
        draw.line(
            [point(x, top_y), point(x, bottom_y)], fill=strings, width=string_width
        )


def gradient(size: int, start: tuple[int, ...], end: tuple[int, ...]) -> Image.Image:
    """Vertical two-colour gradient."""
    image = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        ratio = y / max(1, size - 1)
        draw.line(
            [(0, y), (size, y)],
            fill=tuple(
                round(start[channel] + (end[channel] - start[channel]) * ratio)
                for channel in range(4)
            ),
        )
    return image


def make_icon(size: int, dark: bool) -> Image.Image:
    """Draw the app icon: rounded square with the lyre."""
    canvas = size * SUPERSAMPLE
    top_color, bottom_color = (VIOLET, FUCHSIA) if dark else (INDIGO, VIOLET)
    background = gradient(canvas, top_color, bottom_color)

    mask = Image.new("L", (canvas, canvas), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), (canvas - 1, canvas - 1)], radius=canvas * 0.22, fill=255
    )
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    image.paste(background, (0, 0), mask)

    inset = canvas * 0.14
    draw_lyre(
        ImageDraw.Draw(image),
        inset,
        inset,
        canvas - 2 * inset,
        WHITE,
        STRING_WHITE,
    )
    return image.resize((size, size), Image.LANCZOS)


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Best available semibold sans font."""
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size=size)


def make_logo(height: int, dark: bool) -> Image.Image:
    """Lyre plus wordmark on transparency — the landscape logo.

    Drawn generously, then trimmed to its bounding box: brands wants the
    minimum amount of empty space around the edges, so the width follows from
    the content instead of being fixed.
    """
    work = height * SUPERSAMPLE
    image = Image.new("RGBA", (work * 5, work * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    mark = VIOLET_LIGHT if dark else VIOLET
    text_color = WHITE if dark else INK
    strings = (*mark[:3], 190)

    lyre_size = work * 1.55  # the lyre only fills the middle of its own box
    top = work * 0.2
    left = work * 0.2
    draw_lyre(draw, left, top, lyre_size, mark, strings)

    text = "Barde"
    font = load_font(round(lyre_size * 0.42))
    text_box = draw.textbbox((0, 0), text, font=font)
    lyre_box = image.getbbox()
    draw.text(
        (
            lyre_box[2] + work * 0.16 - text_box[0],
            (lyre_box[1] + lyre_box[3]) / 2 - (text_box[1] + text_box[3]) / 2,
        ),
        text,
        font=font,
        fill=text_color,
    )

    cropped = image.crop(image.getbbox())
    width = round(cropped.width * height / cropped.height)
    return cropped.resize((width, height), Image.LANCZOS)


def main() -> None:
    """Write all eight brand images."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    images = {
        "icon.png": make_icon(256, dark=False),
        "icon@2x.png": make_icon(512, dark=False),
        "dark_icon.png": make_icon(256, dark=True),
        "dark_icon@2x.png": make_icon(512, dark=True),
        "logo.png": make_logo(256, dark=False),
        "logo@2x.png": make_logo(512, dark=False),
        "dark_logo.png": make_logo(256, dark=True),
        "dark_logo@2x.png": make_logo(512, dark=True),
    }
    for name, image in images.items():
        path = OUT_DIR / name
        image.save(path, "PNG", optimize=True)
        print(f"{path.relative_to(REPO)}  {image.size[0]}x{image.size[1]}")


if __name__ == "__main__":
    main()
