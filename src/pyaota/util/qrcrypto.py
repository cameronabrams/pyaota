"""
qrcrypto.py

QR code image generation and lightweight answer encryption for pyaota.

Encryption uses an HMAC-SHA256-based stream cipher (no external dependencies):
  - Keystream derived from HMAC(key, block_counter) — CTR-mode equivalent
  - 8-byte authentication tag appended to the ciphertext
  - Standard base64 encoding (LaTeX-safe: no underscores)

QR payload format:  <version_label>:<base64(ciphertext + 8-byte-mac)>
"""

import base64
import hashlib
import hmac
import secrets
from pathlib import Path

_MAC_LEN = 8  # bytes of HMAC-SHA256 used as authentication tag


def generate_key() -> str:
    """Return a new random 32-byte key as a lowercase hex string."""
    return secrets.token_bytes(32).hex()


def _keystream(key: bytes, length: int) -> bytes:
    """Expand *key* into *length* pseudorandom bytes using HMAC-SHA256."""
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        stream += hmac.new(key, counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(stream[:length])


def encrypt_answers(key_hex: str, answers: list) -> str:
    """
    Encrypt a list of single-character answer strings and return a
    URL-safe base64 payload suitable for embedding in a QR code.

    Answers must already be normalised to single characters
    (True/False → a/b, MCQ choices lower-cased).
    """
    key = bytes.fromhex(key_hex)
    plaintext = "".join(answers).encode()
    stream = _keystream(key, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream))
    tag = hmac.new(key, ciphertext, hashlib.sha256).digest()[:_MAC_LEN]
    return base64.b64encode(ciphertext + tag).decode()


def decrypt_answers(key_hex: str, payload: str) -> list:
    """
    Decrypt a base64 payload produced by *encrypt_answers*.

    Returns a list of single-character answer strings.
    Raises ``ValueError`` if the payload is malformed or the MAC check fails.
    """
    key = bytes.fromhex(key_hex)
    try:
        raw = base64.b64decode(payload)
    except Exception as exc:
        raise ValueError(f"QR payload is not valid base64: {exc}") from exc
    if len(raw) <= _MAC_LEN:
        raise ValueError("QR payload is too short to contain answers and MAC")
    ciphertext, tag = raw[:-_MAC_LEN], raw[-_MAC_LEN:]
    expected_tag = hmac.new(key, ciphertext, hashlib.sha256).digest()[:_MAC_LEN]
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("QR payload MAC verification failed — wrong key or corrupted data")
    stream = _keystream(key, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, stream)).decode()
    return list(plaintext)


# ---------------------------------------------------------------------------
# QR image generation
# ---------------------------------------------------------------------------

def generate_qr_png(
    content: str,
    output_path: Path,
    error_correction: str = "M",
    display_size_cm: float = None,
    scan_dpi: int = 300,
) -> None:
    """
    Generate a QR code PNG for *content* and write it to *output_path*.

    *error_correction* selects the Reed-Solomon level:
      'L' = ~7 %, 'M' = ~15 % (default), 'Q' = ~25 %, 'H' = ~30 %

    After writing the image is decoded with OpenCV at full resolution.
    If *display_size_cm* is given, a second verification is performed by
    downsampling to the expected scan resolution (``display_size_cm`` ×
    ``scan_dpi`` / 2.54 pixels square) so that readability at print size is
    confirmed before the exam PDF is built.

    Requires the ``qrcode[pil]`` package (Pillow is already a dependency).
    """
    import qrcode
    import qrcode.constants
    import cv2
    import numpy as np
    from PIL import Image

    ec_map = {
        "L": qrcode.constants.ERROR_CORRECT_L,
        "M": qrcode.constants.ERROR_CORRECT_M,
        "Q": qrcode.constants.ERROR_CORRECT_Q,
        "H": qrcode.constants.ERROR_CORRECT_H,
    }
    ec = ec_map.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_M)

    qr = qrcode.QRCode(error_correction=ec, box_size=10, border=4)
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(str(output_path))

    # Full-resolution round-trip check
    arr = np.array(img.convert("L"))
    decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(arr)
    if decoded != content:
        raise RuntimeError(
            f"QR round-trip verification failed for '{output_path.name}': "
            f"encoded {content!r}, decoded {decoded!r}"
        )

    # Scan-resolution check: downsample to what a scanner at scan_dpi will see
    if display_size_cm is not None:
        scan_px = round(display_size_cm * scan_dpi / 2.54)
        scan_px = max(scan_px, 1)
        pil_small = img.convert("L").resize((scan_px, scan_px), Image.LANCZOS)
        arr_small = np.array(pil_small)
        decoded_small, _, _ = cv2.QRCodeDetector().detectAndDecode(arr_small)
        if decoded_small != content:
            modules = qr.modules_count if hasattr(qr, "modules_count") else "?"
            px_per_module = scan_px / modules if modules != "?" else "?"
            raise RuntimeError(
                f"QR scan-resolution verification failed for '{output_path.name}': "
                f"at {scan_dpi} DPI / {display_size_cm:.1f} cm "
                f"({scan_px}×{scan_px} px, ~{px_per_module:.1f} px/module) "
                f"the code could not be decoded. "
                f"Consider increasing qr_size or using a lower error-correction level."
            )
