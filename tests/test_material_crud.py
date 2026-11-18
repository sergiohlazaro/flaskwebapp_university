import io
import os

from tests.conftest import login, make_user
from website import db
from website.models import Material, MaterialFile, Subject


def pdf(name="a.pdf", body=b"%PDF-1.4 test"):
    return (io.BytesIO(body), name)


def new_subject(name="Bases de datos", archived=False):
    s = Subject(name=name, is_archived=archived)
    db.session.add(s)
    db.session.commit()
    return s


def post_new(client, subject_id, files=None, **over):
    data = {"title": "Tema 1", "description": "Desc", "subject_id": str(subject_id),
            "course": "", "kind": ""}
    data.update(over)
    data["files"] = [pdf()] if files is None else files
    return client.post("/material/nuevo", data=data, content_type="multipart/form-data")


def setup_author(client, email="a@x.es"):
    user = make_user(email)
    login(client, email)
    return user


def disk_files(app):
    root = os.path.join(app.config["UPLOAD_ROOT"], "materials")
    return os.listdir(root) if os.path.isdir(root) else []


def test_create_material_with_two_files(app, client):
    setup_author(client)
    s = new_subject()
    r = post_new(client, s.id, files=[pdf("a.pdf"), pdf("b.pdf")], course="2º", kind="Apuntes")
    m = Material.query.one()
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/material/{m.id}")
    assert MaterialFile.query.count() == 2
    assert m.course.value == "2º" and m.kind.value == "Apuntes"
    assert len(disk_files(app)) == 2
    assert client.get(f"/material/{m.id}").status_code == 200


def test_requires_login(app, client):
    assert client.get("/material/nuevo").status_code == 302


def test_title_length_limits(app, client):
    setup_author(client)
    s = new_subject()
    for n in (2, 151):
        assert post_new(client, s.id, title="a" * n).status_code == 200
    assert Material.query.count() == 0
    for n in (3, 150):
        assert post_new(client, s.id, title="a" * n).status_code == 302
    assert Material.query.count() == 2


def test_subject_required_and_archived_not_selectable(app, client):
    setup_author(client)
    arch = new_subject("Vieja", archived=True)
    assert post_new(client, "").status_code == 200
    assert post_new(client, arch.id).status_code == 200
    assert post_new(client, 99999).status_code == 200
    assert Material.query.count() == 0
    assert "Vieja" not in client.get("/material/nuevo").get_data(as_text=True)


def test_file_count_limits(app, client):
    setup_author(client)
    s = new_subject()
    r = post_new(client, s.id, files=[])
    assert "Sube al menos un fichero." in r.get_data(as_text=True)
    r = post_new(client, s.id, files=[pdf(f"{i}.pdf") for i in range(6)])
    assert "Máximo 5 ficheros." in r.get_data(as_text=True)
    assert Material.query.count() == 0 and disk_files(app) == []
    assert post_new(client, s.id, files=[pdf(f"{i}.pdf") for i in range(5)]).status_code == 302


def test_invalid_file_shows_form_error_not_500(app, client):
    setup_author(client)
    s = new_subject()
    r = post_new(client, s.id, files=[pdf("ok.pdf"), pdf("bad.pdf", b"<html>")])
    assert r.status_code == 200
    assert "no es un PDF válido" in r.get_data(as_text=True)
    assert Material.query.count() == 0 and disk_files(app) == []
    r = post_new(client, s.id, files=[(io.BytesIO(b"x"), "a.exe")])
    assert r.status_code == 200 and "Tipo de archivo no permitido" in r.get_data(as_text=True)


def test_save_failure_cleans_written_files(app, client, monkeypatch):
    from website.blueprints import materials as mod
    setup_author(client)
    s = new_subject()
    real = mod.save_upload
    calls = []

    def flaky(file, kind, allowed):
        if calls:
            raise mod.UploadError("fallo")
        calls.append(1)
        return real(file, kind, allowed)

    monkeypatch.setattr(mod, "save_upload", flaky)
    r = post_new(client, s.id, files=[pdf("a.pdf"), pdf("b.pdf")])
    assert r.status_code == 200
    assert Material.query.count() == 0 and disk_files(app) == []


def make_material(author, subject, n=1):
    m = Material(title="Orig", description="d", subject_id=subject.id, author_id=author.id)
    db.session.add(m)
    db.session.flush()
    from werkzeug.datastructures import FileStorage

    from website.services.uploads import ALLOWED_MATERIAL_EXTENSIONS, save_upload
    for i in range(n):
        f = save_upload(FileStorage(io.BytesIO(b"%PDF-1.4"), filename=f"f{i}.pdf"),
                        "materials", ALLOWED_MATERIAL_EXTENSIONS)
        m.files.append(MaterialFile(stored_name=f.stored_name, original_name=f.original_name,
                                    mime=f.mime, size=f.size))
    db.session.commit()
    assert len(m.files) == n
    return m


def test_only_author_can_edit(app, client):
    author = make_user("a@x.es")
    make_user("o@x.es")
    make_user("ad@x.es", role=0)
    m = make_material(author, new_subject())
    url = f"/material/{m.id}/editar"
    login(client, "o@x.es")
    assert client.get(url).status_code == 403
    assert client.post(url, data={"title": "Hack"}).status_code == 403
    client.get("/logout")
    login(client, "ad@x.es")
    assert client.get(url).status_code == 403
    client.get("/logout")
    login(client, "a@x.es")
    assert client.get(url).status_code == 200
    r = client.post(url, data={"title": "Nuevo", "description": "", "subject_id": str(m.subject_id),
                               "course": "", "kind": "", "files": []},
                    content_type="multipart/form-data")
    assert r.status_code == 302
    assert db.session.get(Material, m.id).title == "Nuevo"


def test_edit_archived_subject_kept_and_file_limit_counts_existing(app, client):
    author = setup_author(client)
    s = new_subject(archived=True)
    m = make_material(author, s, n=3)
    url = f"/material/{m.id}/editar"
    assert "Bases de datos" in client.get(url).get_data(as_text=True)
    data = {"title": "Nuevo", "description": "", "subject_id": str(s.id), "course": "", "kind": "",
            "files": [pdf(f"n{i}.pdf") for i in range(3)]}
    r = client.post(url, data=data, content_type="multipart/form-data")
    assert r.status_code == 200 and "Máximo 5 ficheros." in r.get_data(as_text=True)
    data["files"] = [pdf("n.pdf")]
    assert client.post(url, data=data, content_type="multipart/form-data").status_code == 302
    assert MaterialFile.query.count() == 4


def test_author_or_admin_can_delete_and_files_removed(app, client):
    author = make_user("a@x.es")
    make_user("o@x.es")
    make_user("ad@x.es", role=0)
    s = new_subject()
    m1 = make_material(author, s, n=2)
    m2 = make_material(author, s, n=1)
    assert len(disk_files(app)) == 3
    login(client, "o@x.es")
    assert client.post(f"/material/{m1.id}/borrar").status_code == 403
    assert len(disk_files(app)) == 3
    client.get("/logout")
    login(client, "a@x.es")
    assert client.post(f"/material/{m1.id}/borrar").status_code == 302
    assert len(disk_files(app)) == 1 and Material.query.count() == 1
    client.get("/logout")
    login(client, "ad@x.es")
    assert client.post(f"/material/{m2.id}/borrar").status_code == 302
    assert disk_files(app) == [] and Material.query.count() == 0


def test_remove_file_author_only_never_last(app, client):
    author = make_user("a@x.es")
    make_user("o@x.es")
    m = make_material(author, new_subject(), n=2)
    f1, f2 = m.files
    url = lambda f: f"/material/{m.id}/ficheros/{f.id}/quitar"
    login(client, "o@x.es")
    assert client.post(url(f1)).status_code == 403
    client.get("/logout")
    login(client, "a@x.es")
    assert client.post(url(f1)).status_code == 302
    assert MaterialFile.query.count() == 1 and len(disk_files(app)) == 1
    r = client.post(url(f2), follow_redirects=True)
    assert r.status_code == 200 and "al menos un fichero" in r.get_data(as_text=True)
    assert MaterialFile.query.count() == 1 and len(disk_files(app)) == 1


def test_description_is_stored_as_plain_text(app, client):
    setup_author(client)
    s = new_subject()
    r = post_new(client, s.id, description="a < b & c")
    assert Material.query.one().description == "a < b & c"
    r = client.get(r.headers["Location"])
    assert r.status_code == 200
    r = client.get(f"/material/{Material.query.one().id}/editar")
    html = r.get_data(as_text=True)
    assert "a &lt; b &amp; c" in html and "&amp;amp;" not in html


def test_detail_hidden_stub(app, client):
    author = make_user("a@x.es")
    make_user("o@x.es")
    m = make_material(author, new_subject())
    m.is_hidden = True
    db.session.commit()
    login(client, "o@x.es")
    assert client.get(f"/material/{m.id}").status_code == 404
    assert client.get("/material/9999").status_code == 404
