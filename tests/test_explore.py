from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import login, make_user
from website import db
from website.models import Course, Material, MaterialFile, MaterialKind, Rating, Subject

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _subject(name):
    subject = Subject(name=name)
    db.session.add(subject)
    db.session.commit()
    return subject


def _material(author, subject, title, minutes=0, **kwargs):
    material = Material(title=title, description=kwargs.pop("description", ""), subject_id=subject.id,
                        author_id=author.id, created_at=BASE + timedelta(minutes=minutes), **kwargs)
    db.session.add(material)
    db.session.commit()
    return material


def _rate(material, *stars):
    for index, value in enumerate(stars):
        voter = make_user(f"v{material.id}-{index}@uni.es")
        db.session.add(Rating(user_id=voter.id, material_id=material.id, stars=value))
    db.session.commit()


@pytest.fixture
def user(app, client):
    account = make_user("ana@uni.es")
    login(client, "ana@uni.es")
    return account


def _titles(response):
    html = response.get_data(as_text=True)
    return [t for t in ("Alfa", "Beta", "Gamma", "Delta") if f">{t}<" in html], html


def test_explore_requires_login(client):
    response = client.get("/explorar")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_home_redirects_to_explore(client, user):
    response = client.get("/home")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/explorar")


def test_search_matches_title_and_description_case_insensitive(app, client, user):
    subject = _subject("Redes")
    _material(user, subject, "Alfa", description="sobre Normalización")
    _material(user, subject, "Beta", description="Normalizacion")
    _material(user, subject, "Gamma")
    found, _ = _titles(client.get("/explorar?q=NORMALIZ"))
    assert found == ["Alfa", "Beta"]
    found, _ = _titles(client.get("/explorar?q=normalizacion"))
    assert found == ["Beta"]  # sin tilde solo coincide la descripción sin acento
    found, _ = _titles(client.get("/explorar?q=gAMMa"))
    assert found == ["Gamma"]


def test_search_escapes_wildcards(app, client, user):
    subject = _subject("Redes")
    _material(user, subject, "Alfa", description="100% seguro")
    _material(user, subject, "Beta", description="nada")
    found, _ = _titles(client.get("/explorar?q=%25"))
    assert found == ["Alfa"]
    found, _ = _titles(client.get("/explorar?q=_"))
    assert found == []


def test_filters_by_subject_course_kind_and_teacher(app, client, user):
    s1, s2 = _subject("Redes"), _subject("Bases")
    teacher = make_user("prof@uni.es", is_teacher=True)
    _material(user, s1, "Alfa", course=Course.FIRST, kind=MaterialKind.NOTES)
    _material(teacher, s1, "Beta", course=Course.SECOND, kind=MaterialKind.EXAM)
    _material(user, s2, "Gamma", course=Course.FIRST, kind=MaterialKind.EXAM)
    assert _titles(client.get(f"/explorar?asignatura={s1.id}"))[0] == ["Alfa", "Beta"]
    assert _titles(client.get("/explorar?curso=1º"))[0] == ["Alfa", "Gamma"]
    assert _titles(client.get("/explorar?tipo=Examen"))[0] == ["Beta", "Gamma"]
    assert _titles(client.get("/explorar?profesores=1"))[0] == ["Beta"]
    assert _titles(client.get(f"/explorar?asignatura={s1.id}&tipo=Examen&curso=2º"))[0] == ["Beta"]


def test_archived_subject_remains_filterable(app, client, user):
    subject = _subject("Vieja")
    subject.is_archived = True
    db.session.commit()
    _material(user, subject, "Alfa")
    html = client.get("/explorar").get_data(as_text=True)
    assert "Vieja" in html
    assert _titles(client.get(f"/explorar?asignatura={subject.id}"))[0] == ["Alfa"]


def test_hidden_material_not_listed_even_for_author(app, client, user):
    subject = _subject("Redes")
    _material(user, subject, "Alfa", is_hidden=True)
    _material(user, subject, "Beta")
    assert _titles(client.get("/explorar"))[0] == ["Beta"]


def test_order_recent_default_and_top_rated(app, client, user):
    subject = _subject("Redes")
    alfa = _material(user, subject, "Alfa", minutes=1)
    beta = _material(user, subject, "Beta", minutes=2)
    gamma = _material(user, subject, "Gamma", minutes=3)
    delta = _material(user, subject, "Delta", minutes=4)
    _rate(alfa, 5)
    _rate(beta, 5, 5)
    _rate(gamma, 4)
    del delta
    html = client.get("/explorar").get_data(as_text=True)
    assert [html.index(f">{t}<") for t in ("Delta", "Gamma", "Beta", "Alfa")] == sorted(
        html.index(f">{t}<") for t in ("Delta", "Gamma", "Beta", "Alfa"))
    html = client.get("/explorar?orden=valorados").get_data(as_text=True)
    order = sorted(("Alfa", "Beta", "Gamma", "Delta"), key=lambda t: html.index(f">{t}<"))
    assert order == ["Beta", "Alfa", "Gamma", "Delta"]  # media, luego votos; sin votos al final


def test_top_rated_ties_break_by_date(app, client, user):
    subject = _subject("Redes")
    alfa = _material(user, subject, "Alfa", minutes=1)
    beta = _material(user, subject, "Beta", minutes=2)
    _rate(alfa, 4)
    _rate(beta, 4)
    html = client.get("/explorar?orden=valorados").get_data(as_text=True)
    assert html.index(">Beta<") < html.index(">Alfa<")


def test_pagination_12_per_page(app, client, user):
    subject = _subject("Redes")
    for i in range(13):
        _material(user, subject, f"Material {i:02d}", minutes=i)
    page1 = client.get("/explorar").get_data(as_text=True)
    assert page1.count('class="card material-card') == 12
    assert "Material 00" not in page1
    page2 = client.get("/explorar?pagina=2").get_data(as_text=True)
    assert page2.count('class="card material-card') == 1
    assert "Material 00" in page2


@pytest.mark.parametrize("qs", ["pagina=0", "pagina=abc", "pagina=999", "asignatura=999999",
                                "asignatura=x", "curso=xyz", "tipo=nope", "orden=hack",
                                "pagina=-3", "asignatura=99999999999999999999", "pagina=99999999999999999999", "profesores=zz"])
def test_malformed_params_never_500(app, client, user, qs):
    subject = _subject("Redes")
    _material(user, subject, "Alfa")
    response = client.get(f"/explorar?{qs}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    if qs == "pagina=999":
        assert "No hay material" in html
    elif qs != "profesores=zz":
        assert ">Alfa<" in html


def test_empty_state(client, user):
    assert "No hay material" in client.get("/explorar").get_data(as_text=True)


def test_htmx_returns_fragment_only(app, client, user):
    subject = _subject("Redes")
    _material(user, subject, "Alfa")
    html = client.get("/explorar", headers={"HX-Request": "true"}).get_data(as_text=True)
    assert "<html" not in html
    assert "material-card" in html
    assert "<html" in client.get("/explorar").get_data(as_text=True)


def test_filter_form_is_htmx_enabled(client, user):
    html = client.get("/explorar").get_data(as_text=True)
    assert 'hx-get="/explorar"' in html
    assert 'hx-push-url="true"' in html
    assert 'method="get"' in html


def test_card_shows_teacher_badge_rating_and_file_count(app, client, user):
    subject = _subject("Redes")
    teacher = make_user("prof@uni.es", name="Marta", surname="Gil", is_teacher=True)
    material = _material(teacher, subject, "Alfa", course=Course.THIRD, kind=MaterialKind.NOTES)
    for n in (1, 2):
        material.files.append(MaterialFile(stored_name=f"s{n}", original_name=f"f{n}.pdf",
                                           mime="application/pdf", size=1))
    db.session.commit()
    _rate(material, 5, 5, 5, 4, 5)
    _material(user, subject, "Beta")
    html = client.get("/explorar").get_data(as_text=True)
    assert "Profesor/a" in html
    assert "Marta" in html
    assert "4,8 (5)" in html
    assert "Redes · 3º · Apuntes" in html
    assert "—" in html  # Beta sin valoraciones
    assert f"/material/{material.id}" in html


@pytest.mark.parametrize("path", ["/material/99999999999999999999",
                                  "/material/99999999999999999999/editar"])
def test_huge_int_url_segment_is_404_not_500(client, user, path):
    assert client.get(path).status_code == 404
