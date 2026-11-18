"""`next` tras caducar la sesión: solo URLs a las que se pueda volver con GET."""
from urllib.parse import parse_qs, urlsplit

HX = {"HX-Request": "true"}


def _next(location):
    return parse_qs(urlsplit(location).query).get("next")


def test_get_request_keeps_full_path_as_next(client):
    r = client.get("/explorar?q=redes&pagina=2")
    assert _next(r.headers["Location"]) == ["/explorar?q=redes&pagina=2"]


def test_post_request_has_no_post_only_next(client):
    r = client.post("/material/1/valorar", data={"stars": "3"})
    assert r.status_code == 302
    assert _next(r.headers["Location"]) is None


def test_post_uses_internal_referrer_path(client):
    r = client.post("/material/1/valorar", data={"stars": "3"},
                    headers={"Referer": "http://localhost/material/1?x=1"})
    assert _next(r.headers["Location"]) == ["/material/1?x=1"]


def test_post_ignores_external_referrer(client):
    r = client.post("/material/1/valorar", data={"stars": "3"}, headers={"Referer": "http://evil.example/x"})
    assert _next(r.headers["Location"]) is None


def test_htmx_post_uses_hx_current_url(client):
    r = client.post("/material/1/guardar", headers={**HX, "HX-Current-URL": "http://localhost/explorar?q=a"})
    assert r.status_code == 401
    assert _next(r.headers["HX-Redirect"]) == ["/explorar?q=a"]


def test_htmx_rejects_external_current_url(client):
    r = client.post("/material/1/guardar", headers={**HX, "HX-Current-URL": "https://evil.example/x"})
    assert _next(r.headers["HX-Redirect"]) is None


def test_htmx_without_current_url_post_has_no_next(client):
    r = client.post("/material/1/guardar", headers=HX)
    assert r.status_code == 401 and _next(r.headers["HX-Redirect"]) is None
