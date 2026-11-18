from datetime import UTC, datetime, timedelta

from sqlalchemy import event

from tests.conftest import login, make_user
from website import db
from website.models import Favorite, Material, MaterialFile, Rating, Subject

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _populate(count, offset=0):
    """Crea `count` materiales con autor, asignatura, ficheros y valoraciones distintos."""
    rater = make_user(f"rater{offset}@x.com", name="Rater")
    for i in range(count):
        n = offset + i
        author = make_user(f"author{n}@x.com", name=f"Autor{n}")
        subject = Subject(name=f"Asignatura {n}")
        db.session.add(subject)
        db.session.commit()
        material = Material(title=f"Material {n}", description="", subject_id=subject.id, author_id=author.id,
                            created_at=BASE + timedelta(minutes=n))
        db.session.add(material)
        db.session.commit()
        for k in range(1 + n % 3):
            db.session.add(MaterialFile(material_id=material.id, stored_name=f"s{n}-{k}", original_name=f"o{k}.pdf",
                                        mime="application/pdf", size=10))
        db.session.add(Rating(user_id=rater.id, material_id=material.id, stars=1 + n % 5))
        db.session.commit()


def _count_queries(client, url):
    db.session.expire_all()  # sin estado precargado de la sesión de test
    statements = []

    def before(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", before)
    try:
        response = client.get(url)
    finally:
        event.remove(db.engine, "before_cursor_execute", before)
    assert response.status_code == 200
    return len(statements)


def test_explore_query_count_constant(app, client):
    make_user("viewer@x.com")
    _populate(3)
    login(client, "viewer@x.com")
    small = _count_queries(client, "/explorar")
    _populate(9, offset=3)
    large = _count_queries(client, "/explorar")
    assert Material.query.count() == 12
    assert small == large


def test_saved_and_profile_query_count_constant(app, client):
    viewer = make_user("viewer@x.com")
    owner = make_user("owner@x.com", name="Dueño")
    login(client, "viewer@x.com")

    def add(count, offset):
        for i in range(count):
            n = offset + i
            subject = Subject(name=f"Tema {n}")
            db.session.add(subject)
            db.session.commit()
            material = Material(title=f"M{n}", description="", subject_id=subject.id, author_id=owner.id,
                                created_at=BASE + timedelta(minutes=n))
            db.session.add(material)
            db.session.commit()
            for k in range(1 + n % 3):
                db.session.add(MaterialFile(material_id=material.id, stored_name=f"s{n}-{k}",
                                            original_name="o.pdf", mime="application/pdf", size=1))
            db.session.add(Rating(user_id=viewer.id, material_id=material.id, stars=3))
            db.session.add(Favorite(user_id=viewer.id, material_id=material.id))
            db.session.commit()

    add(3, 0)
    small = (_count_queries(client, "/guardados"), _count_queries(client, f"/u/{owner.id}"))
    add(9, 3)
    large = (_count_queries(client, "/guardados"), _count_queries(client, f"/u/{owner.id}"))
    assert small == large


def test_pagination_links_have_htmx_and_href(app, client):
    make_user("viewer@x.com")
    _populate(13)
    login(client, "viewer@x.com")
    html = client.get("/explorar?q=Material").get_data(as_text=True)
    link = next(line for line in html.splitlines() if "Siguiente" in line)
    assert 'href="/explorar?q=Material&amp;pagina=2"' in link
    assert 'hx-get="/explorar?q=Material&amp;pagina=2"' in link
    assert 'hx-target="#material-list"' in link
    assert 'hx-push-url="true"' in link


def test_pagination_htmx_request_returns_fragment(app, client):
    make_user("viewer@x.com")
    _populate(13)
    login(client, "viewer@x.com")
    response = client.get("/explorar?pagina=2", headers={"HX-Request": "true"})
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<html" not in html
    assert "Material 0" in html
    assert "HX-Request" in response.headers["Vary"]
