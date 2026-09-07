"""Presentation-only denial keeps its status and does not reflect identity."""

import asyncio

from app.web.routers import auth


def test_denied_fallback_is_neutral_and_has_public_links(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "DENIED_DOCUMENT", tmp_path / "absent.html")
    response = asyncio.run(auth.access_denied())
    body = response.body.decode()
    assert response.status_code == 403
    assert "Chưa thể đăng nhập" in body
    assert "không nằm trong danh sách" not in body
    assert 'href="/home"' in body
    assert "https://github.com/NguyenHaiHung0510/microSched" in body
    assert 'href="https://github.com/NguyenHaiHung0510"' in body


def test_denied_uses_built_document_without_redirect(monkeypatch, tmp_path):
    document = tmp_path / "denied.html"
    document.write_text('<!doctype html><html lang="vi">public denial</html>', encoding="utf-8")
    monkeypatch.setattr(auth, "DENIED_DOCUMENT", document)
    response = asyncio.run(auth.access_denied())
    assert response.status_code == 403
    assert response.body.decode() == document.read_text(encoding="utf-8")
    assert "location" not in response.headers
