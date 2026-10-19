#!/usr/bin/env python3
"""Create resized, metadata-free WebP copies of images in static/images."""
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1] / "static" / "images"
SUPPORTED = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
MAX_SIZE = (2000, 2000)
QUALITY = 82


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    converted = 0
    for source in ROOT.rglob("*"):
        if not source.is_file() or source.suffix.lower() not in SUPPORTED:
            continue
        target = source.with_suffix(".webp")
        if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
            continue
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original)
            image.thumbnail(MAX_SIZE, Image.Resampling.LANCZOS)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            image.save(target, "WEBP", quality=QUALITY, method=6)
        converted += 1
        print(f"{source.relative_to(ROOT)} -> {target.relative_to(ROOT)}")
    print(f"Optimized {converted} image(s). Original files were kept.")


if __name__ == "__main__":
    main()
