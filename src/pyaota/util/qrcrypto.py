"""
qrcrypto.py

QR code image generation and lightweight answer encryption for pyaota.

Encryption uses an HMAC-SHA256-based stream cipher (no external dependencies).
One random key is generated per build and stored in ``answersheet_layout.json``.

Format 2 (current), QR payload ``<version_label>:2.<base64(ciphertext + tag)>``:
  - separate encryption and MAC keys are derived from the build key;
  - the keystream is HMAC(enc_key, version_label || block_counter), so every
    version has its own keystream (the version label is the nonce; labels are
    unique within a build);
  - the 8-byte tag is HMAC(mac_key, "2" || version_label || ciphertext), so a
    payload cannot be moved to another version label.

Format 1 (pyaota 0.5.0), QR payload ``<version_label>:<base64(ciphertext + tag)>``:
one keystream shared by every version of a build, so a student who learned
their own version's answers could XOR them out of their QR code and decrypt
every other version from the same build.  It is still decrypted, so sheets
printed by 0.5.0 can be graded, but no longer written.  The ``2.`` prefix
cannot begin a format-1 payload, because ``.`` is not a base64 character.

Standard base64 is kept (LaTeX-safe: no underscores).
"""

import base64
import hashlib
import hmac
import secrets
from pathlib import Path

_MAC_LEN = 8  # bytes of HMAC-SHA256 used as authentication tag
_FORMAT2_PREFIX = "2."


def generate_key() -> str:
    """Return a new random 32-byte key as a lowercase hex string."""
    return secrets.token_bytes(32).hex()


def _keystream(key: bytes, length: int, nonce: bytes = b"") -> bytes:
    """Expand *key* and *nonce* into *length* pseudorandom bytes using HMAC-SHA256."""
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        stream += hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(stream[:length])


def _subkey(key: bytes, purpose: bytes) -> bytes:
    return hmac.new(key, b"pyaota-qr-" + purpose, hashlib.sha256).digest()


def _xor(data: bytes, stream: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, stream))


def encrypt_answers(key_hex: str, answers: list, version_label: str) -> str:
    """
    Encrypt a list of single-character answer strings for *version_label* and
    return the payload to embed after ``<version_label>:`` in the QR code.

    Answers must already be normalised to single characters
    (True/False → a/b, MCQ choices lower-cased).
    """
    key = bytes.fromhex(key_hex)
    label = version_label.encode()
    plaintext = "".join(answers).encode()
    ciphertext = _xor(plaintext, _keystream(_subkey(key, b"enc"), len(plaintext), nonce=label + b"|"))
    tag = hmac.new(_subkey(key, b"mac"), b"2|" + label + b"|" + ciphertext, hashlib.sha256).digest()[:_MAC_LEN]
    return _FORMAT2_PREFIX + base64.b64encode(ciphertext + tag).decode()


def _split_payload(b64: str) -> tuple[bytes, bytes]:
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception as exc:
        raise ValueError(f"QR payload is not valid base64: {exc}") from exc
    if len(raw) <= _MAC_LEN:
        raise ValueError("QR payload is too short to contain answers and MAC")
    return raw[:-_MAC_LEN], raw[-_MAC_LEN:]


def decrypt_answers(key_hex: str, payload: str, version_label: str) -> list:
    """
    Decrypt a payload produced by *encrypt_answers* (format 2) or by pyaota
    0.5.0 (format 1) for *version_label*.

    Returns a list of single-character answer strings.
    Raises ``ValueError`` if the payload is malformed or the MAC check fails
    (including a format-2 payload read under a different version label).
    """
    key = bytes.fromhex(key_hex)
    if payload.startswith(_FORMAT2_PREFIX):
        label = version_label.encode()
        ciphertext, tag = _split_payload(payload[len(_FORMAT2_PREFIX):])
        expected_tag = hmac.new(_subkey(key, b"mac"), b"2|" + label + b"|" + ciphertext,
                                hashlib.sha256).digest()[:_MAC_LEN]
        stream = _keystream(_subkey(key, b"enc"), len(ciphertext), nonce=label + b"|")
    else:
        ciphertext, tag = _split_payload(payload)
        expected_tag = hmac.new(key, ciphertext, hashlib.sha256).digest()[:_MAC_LEN]
        stream = _keystream(key, len(ciphertext))
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("QR payload MAC verification failed — wrong key, wrong version, or corrupted data")
    return list(_xor(ciphertext, stream).decode())


# ---------------------------------------------------------------------------
# QR image generation and decoding
# ---------------------------------------------------------------------------

def decode_qr(img) -> tuple[str, object]:
    """
    Decode a QR code in *img* (a grayscale or BGR array).

    Returns ``(text, points)``; *text* is empty if nothing was decoded.
    OpenCV's classic detector misses a few percent of valid symbols (seen
    with OpenCV 5.0 on version 3 and 4 codes), so the ArUco-based detector
    is tried when it fails.
    """
    import cv2

    data, points = "", None
    for detector in (cv2.QRCodeDetector(), cv2.QRCodeDetectorAruco()):
        data, points, _ = detector.detectAndDecode(img)
        if data:
            break
    return data, points


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
    decoded, _ = decode_qr(arr)
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
        decoded_small, _ = decode_qr(arr_small)
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
