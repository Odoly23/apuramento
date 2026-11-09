"""2FA TOTP (RFC 6238, SHA-1, 6 digit, 30s) tanpa dependensi luar + kódigu rekuperasaun."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP = 30
DIGITS = 6
WINDOW = 1  # toleransia ±30s


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _hotp(secret, counter, digits=DIGITS):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def totp_at(secret, ts=None, digits=DIGITS):
    return _hotp(secret, int((time.time() if ts is None else ts) // STEP), digits)


def verify(secret, code, last_counter=0, ts=None):
    """Return counter válidu (> last_counter, anti-replay) ka None."""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != DIGITS:
        return None
    now = int((time.time() if ts is None else ts) // STEP)
    for c in range(now - WINDOW, now + WINDOW + 1):
        if c > last_counter and hmac.compare_digest(_hotp(secret, c), code):
            return c
    return None


def otpauth_uri(secret, username, issuer="Apuramentu TL"):
    label = quote(f"{issuer}:{username}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP}"


def make_recovery_codes(n=8):
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(n)]


def hash_code(code):
    return hashlib.sha256(code.strip().lower().replace(" ", "").encode()).hexdigest()
