from app_tracker.security import passwords
from app_tracker.security.passwords import check_password, hash_password


def test_bcrypt_roundtrip():
    h = hash_password("correct horse")
    assert h.startswith(b"$2")  # bcrypt marker
    assert check_password(h, "correct horse")
    assert not check_password(h, "wrong")


def test_empty_inputs_reject():
    h = hash_password("pw")
    assert not check_password(b"", "pw")
    assert not check_password(h, "")


def test_sha256_fallback(monkeypatch):
    monkeypatch.setattr(passwords, "_BCRYPT_AVAILABLE", False)
    h = hash_password("secret")
    assert h.startswith(b"sha256$")
    assert check_password(h, "secret")
    assert not check_password(h, "nope")
