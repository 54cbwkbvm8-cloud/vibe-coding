"""Build the runtime logo and Windows application icon from source images."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "assets" / "source"
BRAND_DIR = ROOT / "assets" / "brand"

LOGO_SCALES = (1, 2, 3)
LOGO_LOGICAL_SIZE = 28
ASSISTANT_BALL_SCALES = (1, 2, 3)
ASSISTANT_BALL_LOGICAL_SIZE = 160
APP_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
APP_ICON_CROP = (20, 405, 1044, 1429)
ASSISTANT_BALL_CROP = (41, 129, 1051, 1309)


def _gradient(size: int, top: str, bottom: str) -> Image.Image:
    top_rgb = tuple(int(top[index : index + 2], 16) for index in (1, 3, 5))
    bottom_rgb = tuple(int(bottom[index : index + 2], 16) for index in (1, 3, 5))
    ratio = np.linspace(0.0, 1.0, size, dtype=np.float32)[:, None, None]
    top_array = np.asarray(top_rgb, dtype=np.float32)[None, None, :]
    bottom_array = np.asarray(bottom_rgb, dtype=np.float32)[None, None, :]
    rgb = top_array * (1.0 - ratio) + bottom_array * ratio
    rgb = np.repeat(rgb, size, axis=1).astype(np.uint8)
    alpha = np.full((size, size, 1), 255, dtype=np.uint8)
    return Image.fromarray(np.concatenate((rgb, alpha), axis=2), "RGBA")


def _circular_mask(size: int) -> Image.Image:
    supersample = 8
    mask = Image.new("L", (size * supersample, size * supersample), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse(
        (0, 0, size * supersample - 1, size * supersample - 1),
        fill=255,
    )
    return mask.resize((size, size), Image.Resampling.LANCZOS)


def _resize_inside(image: Image.Image, target: tuple[int, int]) -> Image.Image:
    ratio = min(target[0] / image.width, target[1] / image.height)
    return image.resize(
        (
            max(1, round(image.width * ratio)),
            max(1, round(image.height * ratio)),
        ),
        Image.Resampling.LANCZOS,
    )


def build_logo(size: int) -> Image.Image:
    source = Image.open(SOURCE_DIR / "IMG_4277.JPG").convert("RGBA")
    mask = Image.open(
        SOURCE_DIR / "IMG_4277_foreground_mask.png"
    ).convert("L")
    mask = mask.filter(ImageFilter.GaussianBlur(0.45))
    source.putalpha(mask)

    canvas_size = size * 4
    badge = _gradient(canvas_size, "#FFF6D9", "#E9B85C")
    subject = _resize_inside(
        source.crop((35, 135, 1045, 1315)),
        (
            round(canvas_size * 0.88),
            round(canvas_size * 0.88),
        ),
    )
    badge.alpha_composite(
        subject,
        (
            (canvas_size - subject.width) // 2,
            (canvas_size - subject.height) // 2,
        ),
    )
    badge.putalpha(_circular_mask(canvas_size))

    ring = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    ring_width = max(2, round(canvas_size * 0.025))
    ImageDraw.Draw(ring).ellipse(
        (
            ring_width,
            ring_width,
            canvas_size - ring_width - 1,
            canvas_size - ring_width - 1,
        ),
        outline=(255, 255, 255, 105),
        width=ring_width,
    )
    badge.alpha_composite(ring)
    return badge.resize((size, size), Image.Resampling.LANCZOS)


def build_assistant_ball(size: int) -> Image.Image:
    """Build a visually centred standing-frog badge for the floating ball."""
    source = Image.open(SOURCE_DIR / "IMG_4277.JPG").convert("RGBA")
    mask = Image.open(
        SOURCE_DIR / "IMG_4277_foreground_mask.png"
    ).convert("L")
    mask = mask.filter(ImageFilter.GaussianBlur(0.45))
    source.putalpha(mask)

    canvas_size = size * 2
    badge = _gradient(canvas_size, "#FFF6D9", "#E9B85C")
    subject = _resize_inside(
        source.crop(ASSISTANT_BALL_CROP),
        (
            round(canvas_size * 0.88),
            round(canvas_size * 0.88),
        ),
    )
    badge.alpha_composite(
        subject,
        (
            (canvas_size - subject.width) // 2,
            (canvas_size - subject.height) // 2,
        ),
    )
    badge.putalpha(_circular_mask(canvas_size))
    return badge.resize((size, size), Image.Resampling.LANCZOS)


def build_app_icon() -> Image.Image:
    source = Image.open(SOURCE_DIR / "IMG_4278.JPG").convert("RGB")
    crop = source.crop(APP_ICON_CROP)
    return crop.resize((1024, 1024), Image.Resampling.LANCZOS)


def main() -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    for scale in LOGO_SCALES:
        size = LOGO_LOGICAL_SIZE * scale
        build_logo(size).save(BRAND_DIR / f"logo@{scale}x.png")

    build_assistant_ball(1024).save(BRAND_DIR / "assistant_ball_1024.png")
    for scale in ASSISTANT_BALL_SCALES:
        size = ASSISTANT_BALL_LOGICAL_SIZE * scale
        build_assistant_ball(size).save(
            BRAND_DIR / f"assistant_ball@{scale}x.png"
        )

    app_icon = build_app_icon()
    app_icon.save(BRAND_DIR / "app_icon_1024.png")
    app_icon.resize((256, 256), Image.Resampling.LANCZOS).save(
        BRAND_DIR / "app_icon.ico",
        format="ICO",
        sizes=[(size, size) for size in APP_ICON_SIZES],
    )


if __name__ == "__main__":
    main()
