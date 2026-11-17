import os
import re

from tests.conftest import login, make_user
from website import create_app


def test_security_headers_present(client):
    r = client.get("/sobre")
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self' https://cdn.jsdelivr.net" in csp
    assert "frame-ancestors 'none'" in csp
    assert "form-action 'self'" in csp
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Strict-Transport-Security" not in r.headers


def test_hsts_only_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-key")
    prod = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    r = prod.test_client().get("/sobre")
    assert r.headers["Strict-Transport-Security"] == "max-age=31536000"


def test_cdn_assets_have_sri(client):
    html = client.get("/sobre").get_data(as_text=True)
    tags = re.findall(r"<(?:script|link)\b[^>]*>", html)
    cdn = [t for t in tags if "cdn.jsdelivr.net" in t]
    assert len(cdn) == 4
    for tag in cdn:
        assert "integrity=" in tag and 'crossorigin="anonymous"' in tag


def test_templates_have_no_inline_styles_or_scripts():
    root = os.path.join(os.path.dirname(__file__), "..", "website", "templates")
    offenders = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != "legacy"]
        for name in names:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                text = fh.read()
            if re.search(r"\sstyle=|<style|\sonclick=|<script(?![^>]*\ssrc=)", text):
                offenders.append(name)
    assert offenders == []


def test_landing_for_visitor_and_redirect_for_user(app, client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Campus Share" in r.get_data(as_text=True)
    make_user("a@example.com")
    login(client, "a@example.com")
    r = client.get("/")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/home")


def test_public_pages_in_spanish(client):
    assert "Aviso legal" in client.get("/aviso-legal").get_data(as_text=True)
    assert "Política de privacidad" in client.get("/privacidad").get_data(as_text=True)
    for url in ("/sobre", "/contacto", "/cookies"):
        assert client.get(url).status_code == 200


def test_old_public_urls_redirect(client):
    for old, new in [("/about", "/sobre"), ("/contact", "/contacto"), ("/legal", "/aviso-legal"),
                     ("/privacy", "/privacidad")]:
        r = client.get(old)
        assert r.status_code == 301
        assert r.headers["Location"].endswith(new)


def test_htmx_request_without_session_gets_hx_redirect(client):
    r = client.get("/home", headers={"HX-Request": "true"})
    assert r.status_code == 401
    assert r.headers["HX-Redirect"].startswith("/login")
    assert "next=" in r.headers["HX-Redirect"]
    assert client.get("/home").status_code == 302


def test_logout_requires_post(app, client):
    make_user("a@example.com")
    login(client, "a@example.com")
    assert client.get("/logout").status_code == 405
    r = client.post("/logout")
    assert r.status_code == 302
    assert r.headers["Location"] in ("/", "http://localhost/")
    assert client.get("/home").status_code == 302
