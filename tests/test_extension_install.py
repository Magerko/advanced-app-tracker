from app_tracker.browser import extension_install as ei


def test_missing_xpi_gives_a_clear_message(tmp_path, monkeypatch):
    monkeypatch.setattr(ei, "signed_xpi_path", lambda: tmp_path / "none.xpi")
    ok, message = ei.install_extension()
    assert not ok
    assert "sign_extension.py" in message


def test_missing_firefox_gives_a_clear_message(tmp_path, monkeypatch):
    xpi = tmp_path / "a.xpi"
    xpi.write_bytes(b"x")
    monkeypatch.setattr(ei, "signed_xpi_path", lambda: xpi)
    monkeypatch.setattr(ei, "find_firefox", lambda: None)
    ok, message = ei.install_extension()
    assert not ok
    assert "Firefox не найден" in message


def test_firefox_is_started_with_the_xpi(tmp_path, monkeypatch):
    xpi = tmp_path / "a.xpi"
    xpi.write_bytes(b"x")
    calls = []
    monkeypatch.setattr(ei, "signed_xpi_path", lambda: xpi)
    monkeypatch.setattr(ei, "find_firefox", lambda: "firefox")
    monkeypatch.setattr(ei.subprocess, "Popen", lambda args: calls.append(args))
    ok, _ = ei.install_extension()
    assert ok
    assert calls == [["firefox", str(xpi)]]
