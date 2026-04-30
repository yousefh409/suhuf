import time
from auth import sign, verify


def test_sign_verify_roundtrip():
    tok = sign("s3cret", "https://app.example", ttl_sec=60)
    assert verify("s3cret", tok)


def test_wrong_secret_fails():
    tok = sign("s3cret", "https://app.example", ttl_sec=60)
    assert not verify("WRONG", tok)


def test_expired_fails():
    tok = sign("s3cret", "https://app.example", ttl_sec=-1)
    assert not verify("s3cret", tok)


def test_origin_mismatch_fails():
    tok = sign("s3cret", "https://app.example", ttl_sec=60)
    assert not verify("s3cret", tok, expected_origin="https://other.example")
