import base64
import hashlib
import hmac
from unittest import TestCase

from pyaota.util.qrcrypto import decrypt_answers, encrypt_answers, generate_key

ANSWERS = list("abcdabcdaabbccddabca")


def _format1_payload(key_hex, answers):
    # pyaota 0.5.0's encoding: one keystream for every version in a build
    key = bytes.fromhex(key_hex)
    pt = "".join(answers).encode()
    stream = b"".join(hmac.new(key, i.to_bytes(4, "big"), hashlib.sha256).digest() for i in range(2))[:len(pt)]
    ct = bytes(a ^ b for a, b in zip(pt, stream))
    return base64.b64encode(ct + hmac.new(key, ct, hashlib.sha256).digest()[:8]).decode()


def _keystream_recovered_by_student(payload, own_answers):
    # XOR the answers a student learned (from their graded overlay) out of their own QR
    body = payload[2:] if payload.startswith("2.") else payload
    ct = base64.b64decode(body)[:-8]
    return bytes(a ^ b for a, b in zip(ct, "".join(own_answers).encode()))


class TestQrCrypto(TestCase):

    def test_round_trip(self):
        key = generate_key()
        payload = encrypt_answers(key, ANSWERS, "6baa9455")
        self.assertTrue(payload.startswith("2."))
        self.assertEqual(decrypt_answers(key, payload, "6baa9455"), ANSWERS)

    def test_format1_payloads_still_decrypt(self):
        key = generate_key()
        self.assertEqual(decrypt_answers(key, _format1_payload(key, ANSWERS), "anything"), ANSWERS)

    def test_one_version_does_not_reveal_another(self):
        key = generate_key()
        other = list("ddddccccbbbbaaaadddd")
        mine = encrypt_answers(key, ANSWERS, "11111111")
        theirs = encrypt_answers(key, other, "22222222")
        stream = _keystream_recovered_by_student(mine, ANSWERS)
        theirs_ct = base64.b64decode(theirs[2:])[:-8]
        recovered = bytes(a ^ b for a, b in zip(theirs_ct, stream)).decode(errors="replace")
        self.assertNotEqual(list(recovered), other)

    def test_format1_was_vulnerable(self):
        # documents why format 2 exists: this attack worked on 0.5.0 payloads
        key = generate_key()
        other = list("ddddccccbbbbaaaadddd")
        stream = _keystream_recovered_by_student(_format1_payload(key, ANSWERS), ANSWERS)
        theirs_ct = base64.b64decode(_format1_payload(key, other))[:-8]
        self.assertEqual(list(bytes(a ^ b for a, b in zip(theirs_ct, stream)).decode()), other)

    def test_payload_bound_to_version_label(self):
        key = generate_key()
        payload = encrypt_answers(key, ANSWERS, "11111111")
        with self.assertRaises(ValueError):
            decrypt_answers(key, payload, "22222222")

    def test_wrong_key_and_tampering_rejected(self):
        key = generate_key()
        payload = encrypt_answers(key, ANSWERS, "11111111")
        with self.assertRaises(ValueError):
            decrypt_answers(generate_key(), payload, "11111111")
        raw = bytearray(base64.b64decode(payload[2:]))
        raw[0] ^= 1
        with self.assertRaises(ValueError):
            decrypt_answers(key, "2." + base64.b64encode(bytes(raw)).decode(), "11111111")
