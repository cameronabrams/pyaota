"""
test_digit_ocr.py

Quick script to test pytesseract on a bunch of per-digit PNGs, e.g.
digit_0.png, digit_1.png, ...

Usage (from the folder containing the PNGs):

    conda activate exams
    python test_digit_ocr.py

Or specify a directory:

    python test_digit_ocr.py --dir path/to/digits
"""

import argparse
import glob
import os

import cv2
import numpy as np
import pytesseract


# If you're using the system Tesseract (recommended on Windows), set this:
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# And if needed:
os.environ["TESSDATA_PREFIX"] = r"C:\Program Files\Tesseract-OCR\tessdata"


def ocr_digit_image(path: str) -> str:
    """Run Tesseract on a single pre-thresholded digit image."""
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return "<cannot read>"

    # Just in case: upscale a bit
    h, w = img.shape
    if h < 40 or w < 40:
        img = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    # Ensure it's binary (your image_thresh probably already is)
    _, img_bin = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Try a couple of configs to see what works best
    configs = [
        ("psm10", "--psm 10 --oem 3"),# -c tessedit_char_whitelist=ols0123456789"),
        ("psm13", "--psm 13 --oem 3"),# -c tessedit_char_whitelist=ols0123456789"),
    ]

    results = []
    for label, cfg in configs:
        txt = pytesseract.image_to_string(img_bin, config=cfg)
        txt = txt.strip()
        # Keep only digits for clarity
        digits_only = "".join(ch for ch in txt if ch.isdigit())
        results.append((label, txt, digits_only))

    # Build a compact summary string
    parts = []
    for label, raw, digits_only in results:
        parts.append(f"{label}: raw='{raw}' digits='{digits_only}'")

    return " | ".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dir",
        default=".",
        help="Directory containing digit PNGs (default: current directory)",
    )
    parser.add_argument(
        "--pattern",
        default="digit_*.png",
        help="Glob pattern for digit images (default: digit_*.png)",
    )
    args = parser.parse_args()

    pattern = os.path.join(args.dir, args.pattern)
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"No files found matching {pattern!r}")
        return

    print(f"Found {len(files)} files:")
    for path in files:
        base = os.path.basename(path)
        result = ocr_digit_image(path)
        print(f"{base:25s} -> {result}")


if __name__ == "__main__":
    main()
