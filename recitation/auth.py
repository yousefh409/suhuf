"""Symmetric HMAC token: base64url(payload).hexdigest(hmac_sha256(secret, payload))

payload is JSON {origin, exp}. Same secret on reader (Next.js) and server.
"""
import base64
import hashlib
import hmac
import json
import time


def sign(secret: str, origin: str, ttl_sec: int = 300) -> str:
    payload = {"origin": origin, "exp": int(time.time()) + ttl_sec}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    p64 = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    sig = hmac.new(secret.encode(), p64.encode(), hashlib.sha256).hexdigest()
    return f"{p64}.{sig}"


def verify(secret: str, token: str, expected_origin: str | None = None) -> bool:
    try:
        p64, sig = token.split(".", 1)
    except ValueError:
        return False
    expected = hmac.new(secret.encode(), p64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        pad = "=" * (-len(p64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(p64 + pad))
    except Exception:
        return False
    if int(payload.get("exp", 0)) < int(time.time()):
        return False
    if expected_origin and payload.get("origin") != expected_origin:
        return False
    return True
