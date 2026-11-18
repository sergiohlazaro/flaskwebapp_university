import io
import os

from PIL import Image

from tests.conftest import PASSWORD, login, make_user, png_bytes
from website import db
from website.models import (
    Comment,
    Favorite,
    LoginRecord,
    Material,
    MaterialFile,
    Message,
    Rating,
    Report,
    ReportReason,
    ReportTarget,
    Subject,
    User,
)
from website.services.uploads import upload_path


def _subject():
    subject = Subject(name="Álgebra")
    db.session.add(subject)
    db.session.commit()
    return subject


def _material(author, subject, title="Apuntes", hidden=False, stored=None):
    material = Material(title=title, author_id=author.id, subject_id=subject.id, is_hidden=hidden)
    if stored:
        material.files.append(MaterialFile(stored_name=stored, original_name="a.txt", mime="text/plain", size=1))
    db.session.add(material)
    db.session.commit()
    return material


def _profile_data(**overrides):
    data = {"name": "Ana", "surname": "García", "bio": "Hola", "twitter": "", "linkedin": ""}
    data.update(overrides)
    return data


# --- Perfil público ---------------------------------------------------------

def test_profile_by_id_hides_email(app, client):  # SEC-17
    user = make_user("secreto@example.com", name="Ana", surname="Ruiz", is_teacher=True)
    user.twitter = "ana_g"
    user.linkedin = "ana-ruiz"
    user.bio = "Línea 1\nLínea 2"
    db.session.commit()
    make_user("viewer@example.com")
    login(client, "viewer@example.com")
    r = client.get(f"/u/{user.id}")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "secreto@example.com" not in html
    assert "Ana Ruiz" in html and "Profesor/a" in html
    assert "https://x.com/ana_g" in html and "https://www.linkedin.com/in/ana-ruiz" in html
    assert 'rel="noopener noreferrer"' in html
    assert "Enviar mensaje" in html
    assert client.get("/u/99999").status_code == 404
    assert client.get("/viewuser/secreto@example.com").status_code == 404


def test_profile_requires_login(client):
    assert client.get("/u/1").status_code == 302


def test_profile_lists_only_visible_materials(app, client):
    owner = make_user("o@example.com")
    subject = _subject()
    _material(owner, subject, "Visible uno")
    _material(owner, subject, "Escondido", hidden=True)
    make_user("v@example.com")
    login(client, "v@example.com")
    html = client.get(f"/u/{owner.id}").get_data(as_text=True)
    assert "Visible uno" in html and "Escondido" not in html
    client.post("/logout")
    login(client, "o@example.com")
    html = client.get(f"/u/{owner.id}").get_data(as_text=True)
    assert "Visible uno" in html and "Escondido" in html and "Oculto" in html


def test_profile_paginates_12_and_bounds_page(app, client):
    owner = make_user("o@example.com")
    subject = _subject()
    for i in range(13):
        _material(owner, subject, f"Mat{i:02d}")
    login(client, "o@example.com")
    assert client.get(f"/u/{owner.id}").get_data(as_text=True).count("material-card") == 12
    assert "Mat00" in client.get(f"/u/{owner.id}?pagina=2").get_data(as_text=True)
    assert client.get(f"/u/{owner.id}?pagina=99999999999999999999999").status_code == 200


def test_blocked_profile_only_for_admins(app, client):
    blocked = make_user("b@example.com")
    blocked.is_blocked = True
    db.session.commit()
    make_user("v@example.com")
    login(client, "v@example.com")
    assert client.get(f"/u/{blocked.id}").status_code == 404
    client.post("/logout")
    make_user("a@example.com", role=0)
    login(client, "a@example.com")
    assert client.get(f"/u/{blocked.id}").status_code == 200


# --- Mi cuenta: perfil -------------------------------------------------------

def test_account_page_has_five_forms(client):
    make_user("u@example.com")
    login(client, "u@example.com")
    html = client.get("/cuenta").get_data(as_text=True)
    for action in ("perfil", "avatar", "email", "password", "borrar"):
        assert f'action="/cuenta/{action}"' in html
    assert "u@example.com" in html  # su propio email, solo en su cuenta
    assert client.get("/cuenta", follow_redirects=False).status_code == 200


def test_update_bio_max_300_and_social_regex(app, client):
    user = make_user("u@example.com")
    login(client, "u@example.com")
    r = client.post("/cuenta/perfil", data=_profile_data(bio="A" * 301))
    assert r.status_code == 200 and "300" in r.get_data(as_text=True)
    for bad in ("user name", "https://x.com/u", "a" * 51):
        r = client.post("/cuenta/perfil", data=_profile_data(twitter=bad))
        assert r.status_code == 200
        r = client.post("/cuenta/perfil", data=_profile_data(linkedin=bad))
        assert r.status_code == 200
    assert db.session.get(User, user.id).twitter is None
    r = client.post("/cuenta/perfil", data=_profile_data(bio="A" * 300, twitter="ana_g.99", linkedin="a-b"))
    assert r.status_code == 302
    db.session.expire_all()
    saved = db.session.get(User, user.id)
    assert (saved.bio, saved.twitter, saved.linkedin) == ("A" * 300, "ana_g.99", "a-b")
    r = client.post("/cuenta/perfil", data=_profile_data(twitter="", linkedin="", surname="G"))
    assert r.status_code == 200  # apellidos 2-100
    r = client.post("/cuenta/perfil", data=_profile_data(), follow_redirects=True)
    assert "Perfil actualizado." in r.get_data(as_text=True)
    db.session.expire_all()
    assert db.session.get(User, user.id).twitter in ("", None)


def test_bio_is_escaped_on_profile(app, client):
    user = make_user("u@example.com")
    login(client, "u@example.com")
    client.post("/cuenta/perfil", data=_profile_data(bio="<script>alert(1)</script>"))
    html = client.get(f"/u/{user.id}").get_data(as_text=True)
    assert "<script>alert(1)" not in html


# --- Avatar ------------------------------------------------------------------

def _avatar_post(client, fileobj, name):
    return client.post("/cuenta/avatar", data={"avatar": (fileobj, name)},
                       content_type="multipart/form-data", follow_redirects=True)


def test_avatar_upload_resized_and_mpo_accepted(app, client):  # sustituye QA-01
    user = make_user("pic@example.com")
    login(client, "pic@example.com")
    r = _avatar_post(client, png_bytes(size=(800, 600)), "avatar.png")
    assert "Foto de perfil actualizada." in r.get_data(as_text=True)
    stored = db.session.get(User, user.id).avatar
    assert stored is not None
    with Image.open(upload_path("avatars", stored)) as image:
        assert image.width <= 300 and image.height <= 300
    mpo = io.BytesIO()
    Image.new("RGB", (10, 10)).save(mpo, format="MPO", save_all=True, append_images=[Image.new("RGB", (10, 10))])
    mpo.seek(0)
    r = _avatar_post(client, mpo, "IMG_0001.jpg")
    assert "Foto de perfil actualizada." in r.get_data(as_text=True)
    db.session.expire_all()
    new = db.session.get(User, user.id).avatar
    assert new != stored
    assert not os.path.exists(upload_path("avatars", stored))  # la anterior se borra
    assert os.path.exists(upload_path("avatars", new))


def test_avatar_fake_image_rejected(app, client):
    user = make_user("fake@example.com")
    login(client, "fake@example.com")
    r = client.post("/cuenta/avatar", data={"avatar": (io.BytesIO(b"<script>alert(1)</script>"), "evil.png")},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert db.session.get(User, user.id).avatar is None
    r = client.post("/cuenta/avatar", data={}, content_type="multipart/form-data")
    assert r.status_code == 200


def test_avatar_named_default_cannot_overwrite_shared_default(app, client):  # sustituye SEC-05
    default_path = os.path.join(app.root_path, "static", "profile_pics", "default.jpg")
    with open(default_path, "rb") as fh:
        original = fh.read()
    user = make_user("evil@example.com")
    login(client, "evil@example.com")
    jpeg = io.BytesIO()
    Image.new("RGB", (10, 10), "blue").save(jpeg, format="JPEG")
    jpeg.seek(0)
    client.post("/cuenta/avatar", data={"avatar": (jpeg, "default.jpg")},
                content_type="multipart/form-data")
    try:
        with open(default_path, "rb") as fh:
            assert fh.read() == original
    finally:
        with open(default_path, "wb") as fh:
            fh.write(original)
    stored = db.session.get(User, user.id).avatar
    assert stored is not None and stored != "default.jpg"
    assert os.path.exists(upload_path("avatars", stored))


# --- Email -------------------------------------------------------------------

def test_change_email_requires_current_password(app, client):  # SEC-15
    user = make_user("old@example.com")
    login(client, "old@example.com")
    r = client.post("/cuenta/email", data={"new_email": "new@example.com", "current_password": "mala"})
    assert r.status_code == 200
    assert "La contraseña actual no es correcta." in r.get_data(as_text=True)
    assert db.session.get(User, user.id).email == "old@example.com"
    r = client.post("/cuenta/email", data={"new_email": "new@example.com", "current_password": PASSWORD},
                    follow_redirects=True)
    assert "Email actualizado." in r.get_data(as_text=True)
    db.session.expire_all()
    assert db.session.get(User, user.id).email == "new@example.com"


def test_change_email_normalizes_and_rejects_duplicate(app, client):
    user = make_user("old@example.com")
    make_user("taken@example.com")
    login(client, "old@example.com")
    r = client.post("/cuenta/email", data={"new_email": "  TAKEN@Example.com ", "current_password": PASSWORD})
    assert r.status_code == 200
    assert "Ya existe una cuenta con ese email." in r.get_data(as_text=True)
    r = client.post("/cuenta/email", data={"new_email": "no-es-email", "current_password": PASSWORD})
    assert r.status_code == 200
    client.post("/cuenta/email", data={"new_email": "  NEW@Example.com ", "current_password": PASSWORD})
    db.session.expire_all()
    assert db.session.get(User, user.id).email == "new@example.com"


# --- Contraseña --------------------------------------------------------------

def test_change_password_rules(app, client):
    from werkzeug.security import check_password_hash
    user = make_user("u@example.com")
    login(client, "u@example.com")

    def post(current=PASSWORD, new="nuevaclave1", confirm="nuevaclave1"):
        return client.post("/cuenta/password", data={"current_password": current, "new_password": new,
                                                      "confirm_password": confirm})
    assert post(current="mala").status_code == 200
    assert post(new="corta", confirm="corta").status_code == 200
    assert post(confirm="otra-distinta").status_code == 200
    db.session.expire_all()
    assert check_password_hash(db.session.get(User, user.id).password, PASSWORD)
    assert post().status_code == 302
    db.session.expire_all()
    assert check_password_hash(db.session.get(User, user.id).password, "nuevaclave1")


# --- Borrar cuenta -----------------------------------------------------------

def test_delete_account_requires_password_and_cleans_up(app, client):
    from werkzeug.datastructures import FileStorage

    from website.services.uploads import save_avatar
    victim = make_user("victim@example.com")
    other = make_user("other@example.com")
    subject = _subject()
    avatar = save_avatar(FileStorage(stream=png_bytes(), filename="a.png"))
    victim.avatar = avatar.stored_name
    db.session.commit()
    os.makedirs(os.path.dirname(upload_path("materials", "x.txt")), exist_ok=True)
    mine = _material(victim, subject, "Mío", stored="mine.txt")
    with open(upload_path("materials", "mine.txt"), "wb") as fh:
        fh.write(b"x")
    theirs = _material(other, subject, "Ajeno")
    db.session.add_all([
        Comment(material_id=theirs.id, author_id=victim.id, body="hola"),
        Comment(material_id=mine.id, author_id=other.id, body="en el mío"),
        Rating(user_id=victim.id, material_id=theirs.id, stars=4),
        Rating(user_id=other.id, material_id=mine.id, stars=5),
        Favorite(user_id=victim.id, material_id=theirs.id),
        Favorite(user_id=other.id, material_id=mine.id),
        Report(reporter_id=victim.id, target_type=ReportTarget.MATERIAL, target_id=theirs.id,
               reason=ReportReason.OTHER),
        LoginRecord(user_id=victim.id, ip_address="1.1.1.1"),
        Message(sender_id=victim.id, receiver_id=other.id, content="adiós", file_stored_name=None),
        Message(sender_id=victim.id, receiver_id=None, content="huérfano", file_stored_name="orphan.txt"),
    ])
    db.session.commit()
    os.makedirs(os.path.dirname(upload_path("messages", "orphan.txt")), exist_ok=True)
    with open(upload_path("messages", "orphan.txt"), "wb") as fh:
        fh.write(b"x")
    victim_id, other_id = victim.id, other.id
    login(client, "victim@example.com")

    r = client.post("/cuenta/borrar", data={"current_password": "mala", "confirm": "y"})
    assert r.status_code == 200
    r = client.post("/cuenta/borrar", data={"current_password": PASSWORD})
    assert r.status_code == 200  # falta la confirmación
    assert db.session.get(User, victim_id) is not None

    r = client.post("/cuenta/borrar", data={"current_password": PASSWORD, "confirm": "y"})
    assert r.status_code == 302
    db.session.expire_all()
    assert db.session.get(User, victim_id) is None
    assert db.session.get(Material, mine.id) is None
    assert Comment.query.filter_by(author_id=victim_id).count() == 0
    assert Rating.query.filter_by(user_id=victim_id).count() == 0
    assert Favorite.query.filter_by(user_id=victim_id).count() == 0
    assert Report.query.count() == 0
    assert LoginRecord.query.count() == 0
    assert Comment.query.count() == 0 and Rating.query.count() == 0 and Favorite.query.count() == 0
    assert db.session.get(User, other_id) is not None and db.session.get(Material, theirs.id) is not None
    kept = Message.query.filter_by(content="adiós").one()
    assert kept.sender_id is None and kept.receiver_id == other_id
    assert Message.query.filter_by(content="huérfano").count() == 0  # conversación sin participantes
    assert not os.path.exists(upload_path("avatars", avatar.stored_name))
    assert not os.path.exists(upload_path("materials", "mine.txt"))
    assert not os.path.exists(upload_path("messages", "orphan.txt"))
    assert client.get("/cuenta").status_code == 302  # sesión cerrada


def test_delete_account_failure_keeps_files(app, client, monkeypatch):
    victim = make_user("victim@example.com")
    subject = _subject()
    _material(victim, subject, "Mío", stored="mine.txt")
    os.makedirs(os.path.dirname(upload_path("materials", "mine.txt")), exist_ok=True)
    with open(upload_path("materials", "mine.txt"), "wb") as fh:
        fh.write(b"x")
    login(client, "victim@example.com")
    from sqlalchemy.exc import SQLAlchemyError
    monkeypatch.setattr(db.session, "commit", lambda: (_ for _ in ()).throw(SQLAlchemyError("boom")))
    app.config["PROPAGATE_EXCEPTIONS"] = False
    r = client.post("/cuenta/borrar", data={"current_password": PASSWORD, "confirm": "y"})
    assert r.status_code == 500
    assert os.path.exists(upload_path("materials", "mine.txt"))


def test_last_admin_cannot_delete_account(app, client):  # SEC-18
    admin = make_user("admin@example.com", role=0)
    login(client, "admin@example.com")
    r = client.post("/cuenta/borrar", data={"current_password": PASSWORD, "confirm": "y"}, follow_redirects=True)
    assert r.status_code == 400
    assert "último administrador" in r.get_data(as_text=True)
    assert db.session.get(User, admin.id) is not None
    make_user("admin2@example.com", role=0)
    r = client.post("/cuenta/borrar", data={"current_password": PASSWORD, "confirm": "y"})
    assert r.status_code == 302
    assert db.session.get(User, admin.id) is None


# --- Directorio --------------------------------------------------------------

def test_directory_search_and_no_emails(app, client):
    make_user("ana@uni.es", name="Ana", surname="Pérez", is_teacher=True)
    make_user("luis@uni.es", name="Luis", surname="Gómez")
    blocked = make_user("bloq@uni.es", name="Anabel", surname="Bloqueada")
    blocked.is_blocked = True
    make_user("100@uni.es", name="Cien", surname="100%")
    db.session.commit()
    make_user("me@uni.es", name="Yo", surname="Mismo")
    login(client, "me@uni.es")
    html = client.get("/usuarios").get_data(as_text=True)
    assert "Ana Pérez" in html and "Luis Gómez" in html and "Profesor/a" in html
    assert "Anabel" not in html
    assert "@uni.es" not in html.replace("me@uni.es", "")
    html = client.get("/usuarios?q=ANA").get_data(as_text=True)
    assert "Ana Pérez" in html and "Luis" not in html
    html = client.get("/usuarios?q=100%25").get_data(as_text=True)
    assert "Cien" in html and "Ana Pérez" not in html
    assert client.get("/usuarios?pagina=99999999999999999999999").status_code == 200


def test_directory_paginates_24(app, client):
    for i in range(25):
        make_user(f"u{i}@uni.es", name=f"Nombre{i:02d}", surname="Apellido")
    login(client, "u0@uni.es")
    assert client.get("/usuarios").get_data(as_text=True).count("user-card") == 24
    assert client.get("/usuarios?pagina=2").get_data(as_text=True).count("user-card") == 1


# --- Rutas antiguas ----------------------------------------------------------

def test_old_urls_redirect(client):
    for old, new in (("/profile", "/cuenta"), ("/userlist", "/usuarios"), ("/publications", "/explorar")):
        r = client.get(old)
        assert r.status_code == 301 and r.headers["Location"].endswith(new)
    assert client.get("/viewuser/a@b.com").status_code == 404


def test_account_post_routes_require_login(client):
    for path in ("perfil", "avatar", "email", "password", "borrar"):
        assert client.post(f"/cuenta/{path}").status_code == 302
