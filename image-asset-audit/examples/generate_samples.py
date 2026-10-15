"""Generate a repeatable fictional image batch (no external downloads)."""

from pathlib import Path

from PIL import Image, ImageDraw


def generate(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    big = Image.new("RGB", (640, 480), (32, 68, 112))
    draw = ImageDraw.Draw(big)
    draw.rectangle((80, 80, 560, 400), outline=(240, 220, 90), width=7)
    big.save(directory / "01-banner.png")
    (directory / "02-banner-copy.png").write_bytes(
        (directory / "01-banner.png").read_bytes()
    )
    Image.new("RGB", (120, 90), (200, 110, 60)).save(
        directory / "03-thumbnail.jpg", quality=93
    )
    (directory / "04-damaged.png").write_bytes(b"not a real PNG image")


if __name__ == "__main__":
    import sys

    generate(Path(sys.argv[1] if len(sys.argv) > 1 else "sample-images"))
