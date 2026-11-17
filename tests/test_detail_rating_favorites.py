from datetime import UTC, datetime, timedelta

from tests.conftest import login, make_user
from website import db
from website.models import Favorite, Material, MaterialFile, Rating, Subject


def _material(author, title="Apuntes de redes", hidden=False, files=(("Tema 1.pdf", "application/pdf", 2048),)):
    subject = Subject.query.first() or Subject(name="Redes")
    db.session.add(subject)
    db.session.commit()
    material = Material(title=title, description="Línea 1\nLínea 2", subject_id=subject.id,
                        author_id=author.id, is_hidden=hidden)
    for index, (name, mime, size) in enumerate(files):
        material.files.append(MaterialFile(stored_name=f"s{index}-{name}", original_name=name, mime=mime, size=size))
    db.session.add(material)
    db.session.commit()
    return material


def _setup(client):
    author = make_user("autor@uni.es", name="Autor")
    viewer = make_user("lector@uni.es", name="Lector")
    material = _material(author)
    login(client, "lector@uni.es")
    return author, viewer, material


def test_detail_shows_files_rating_and_actions(app, client):
    author, _, _ = _setup(client)
    material = _material(author, files=(("Tema 1.pdf", "application/pdf", 2048), ("foto.png", "image/png", 3 * 1024 * 1024)))
    body = client.get(f"/material/{material.id}").get_data(as_text=True)
    assert "Tema 1.pdf" in body and "2,0 KB" in body and "3,0 MB" in body
    assert "Descargar" in body
    assert "<img" in body and "/archivos/material/" in body
    assert "Valorar con 5 estrellas" in body
    assert "Guardar" in body
    assert "/editar" not in body and "/borrar" not in body
    assert "id=\"comments\"" in body
    login(client, "autor@uni.es")
    body = client.get(f"/material/{material.id}").get_data(as_text=True)
    assert "/editar" in body and "/borrar" in body
    assert "Valorar con 5 estrellas" not in body


def test_hidden_detail_404_for_others_visible_for_author_with_notice(app, client):
    author = make_user("autor@uni.es")
    make_user("lector@uni.es")
    admin = make_user("adm@uni.es", role=0)
    material = _material(author, hidden=True)
    login(client, "lector@uni.es")
    assert client.get(f"/material/{material.id}").status_code == 404
    login(client, "autor@uni.es")
    res = client.get(f"/material/{material.id}")
    assert res.status_code == 200 and "Oculto por moderación" in res.get_data(as_text=True)
    login(client, "adm@uni.es")
    body = client.get(f"/material/{material.id}").get_data(as_text=True)
    assert "Oculto por moderación" in body and "/borrar" in body
    assert admin.is_admin


def test_rate_create_update_and_remove(app, client):
    _, viewer, material = _setup(client)
    url = f"/material/{material.id}/valorar"
    assert client.post(url, data={"stars": "4"}).status_code == 302
    assert db.session.get(Rating, (viewer.id, material.id)).stars == 4
    client.post(url, data={"stars": "2"})
    db.session.expire_all()
    assert db.session.get(Rating, (viewer.id, material.id)).stars == 2
    client.post(url, data={"stars": "0"})
    db.session.expire_all()
    assert db.session.get(Rating, (viewer.id, material.id)) is None
    assert client.post(url, data={"stars": "0"}).status_code == 302


def test_cannot_rate_own_material(app, client):
    author = make_user("autor@uni.es")
    material = _material(author)
    login(client, "autor@uni.es")
    assert client.post(f"/material/{material.id}/valorar", data={"stars": "5"}).status_code == 403
    assert Rating.query.count() == 0


def test_stars_out_of_range_rejected(app, client):
    _, _, material = _setup(client)
    for value in ("6", "x", "-1", "", "99999999999999999999"):
        assert client.post(f"/material/{material.id}/valorar", data={"stars": value}).status_code == 400
    assert client.post(f"/material/{material.id}/valorar").status_code == 400
    assert Rating.query.count() == 0


def test_rate_requires_login_and_hidden_404(app, client):
    author = make_user("autor@uni.es")
    make_user("lector@uni.es")
    material = _material(author, hidden=True)
    assert client.post(f"/material/{material.id}/valorar", data={"stars": "3"}).status_code == 302
    login(client, "lector@uni.es")
    assert client.post(f"/material/{material.id}/valorar", data={"stars": "3"}).status_code == 404
    assert client.post(f"/material/{material.id}/guardar").status_code == 404
    assert client.post("/material/99999/valorar", data={"stars": "3"}).status_code == 404


def test_double_rating_submit_is_idempotent(app, client):
    _, _, material = _setup(client)
    url = f"/material/{material.id}/valorar"
    assert client.post(url, data={"stars": "5"}, headers={"HX-Request": "true"}).status_code == 200
    assert client.post(url, data={"stars": "5"}, headers={"HX-Request": "true"}).status_code == 200
    assert Rating.query.count() == 1


def test_favorite_toggle_twice_and_saved_page(app, client):
    _, _, material = _setup(client)
    url = f"/material/{material.id}/guardar"
    client.post(url)
    assert Favorite.query.count() == 1
    assert "Apuntes de redes" in client.get("/guardados").get_data(as_text=True)
    client.post(url)
    assert Favorite.query.count() == 0
    client.post(url)
    assert Favorite.query.count() == 1


def test_saved_page_is_private_and_excludes_hidden(app, client):
    author = make_user("autor@uni.es")
    me = make_user("lector@uni.es")
    other = make_user("otro@uni.es")
    visible = _material(author, title="Visible")
    hidden = _material(author, title="Escondido")
    other_only = _material(author, title="Del otro")
    now = datetime(2026, 1, 1, tzinfo=UTC)
    db.session.add_all([Favorite(user_id=me.id, material_id=visible.id, created_at=now),
                        Favorite(user_id=me.id, material_id=hidden.id, created_at=now + timedelta(hours=1)),
                        Favorite(user_id=other.id, material_id=other_only.id)])
    hidden.is_hidden = True
    db.session.commit()
    assert client.get("/guardados").status_code == 302
    login(client, "lector@uni.es")
    body = client.get("/guardados").get_data(as_text=True)
    assert "Visible" in body and "Escondido" not in body and "Del otro" not in body
    login(client, "otro@uni.es")
    assert "Visible" not in client.get("/guardados").get_data(as_text=True)


def test_saved_empty_state_and_bad_page(app, client):
    make_user("lector@uni.es")
    login(client, "lector@uni.es")
    assert "Aún no has guardado ningún material." in client.get("/guardados").get_data(as_text=True)
    assert client.get("/guardados?pagina=abc").status_code == 200
    assert client.get("/guardados?pagina=999").status_code == 200


def test_htmx_rate_returns_partial(app, client):
    _, _, material = _setup(client)
    res = client.post(f"/material/{material.id}/valorar", data={"stars": "3"}, headers={"HX-Request": "true"})
    body = res.get_data(as_text=True)
    assert res.status_code == 200 and "<html" not in body
    assert "Tu valoración" in body and "3,0" in body
    res = client.post(f"/material/{material.id}/guardar", headers={"HX-Request": "true"})
    assert res.status_code == 200 and "<html" not in res.get_data(as_text=True)
    assert "Quitar de guardados" in res.get_data(as_text=True)


def test_redirect_only_to_internal_referrer(app, client):
    _, _, material = _setup(client)
    url = f"/material/{material.id}/guardar"
    res = client.post(url, headers={"Referer": "http://localhost/explorar?x=1"})
    assert res.headers["Location"].endswith("/explorar?x=1")
    res = client.post(url, headers={"Referer": "https://evil.example/x"})
    assert res.headers["Location"].endswith(f"/material/{material.id}")


def test_feed_card_shows_saved_state(app, client):
    _, _, material = _setup(client)
    client.post(f"/material/{material.id}/guardar")
    body = client.get("/explorar").get_data(as_text=True)
    assert "Quitar de guardados" in body


def test_edited_marker_only_after_edit(app, client):
    _, _, material = _setup(client)
    assert material.updated_at == material.created_at
    assert "(editado)" not in client.get(f"/material/{material.id}").get_data(as_text=True)
    material.title = "Cambiado"
    db.session.commit()
    assert "(editado)" in client.get(f"/material/{material.id}").get_data(as_text=True)
