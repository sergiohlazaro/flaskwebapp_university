import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import text

from tests.conftest import login, make_user
from website import create_app, db
from website.models import Material, Subject
from website.services import search
from website.services.search import build_match

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _subject(name):
    subject = Subject(name=name)
    db.session.add(subject)
    db.session.commit()
    return subject


def _material(author, subject, title, description="", minutes=0, **kwargs):
    material = Material(title=title, description=description, subject_id=subject.id, author_id=author.id,
                        created_at=BASE + timedelta(minutes=minutes), **kwargs)
    db.session.add(material)
    db.session.commit()
    return material


@pytest.fixture
def user(app, client):
    account = make_user("ana@uni.es", name="Ana", surname="García")
    login(client, "ana@uni.es")
    return account


def _found(client, q, extra=""):
    html = client.get(f"/explorar?q={q}{extra}").get_data(as_text=True)
    return [t for t in ("Alfa", "Beta", "Gamma", "Delta") if f">{t}<" in html]


def _fts_ids():
    return sorted(r[0] for r in db.session.execute(text("SELECT rowid FROM material_fts")))


def test_search_ignores_accents_and_case(app, client, user):
    _material(user, _subject("Redes"), "Alfa", "Álgebra lineal")
    assert _found(client, "algebra") == ["Alfa"]
    assert _found(client, "ÁLGEBRA") == ["Alfa"]


def test_search_prefix(app, client, user):
    _material(user, _subject("Redes"), "Alfa", "Normalización")
    assert _found(client, "normaliz") == ["Alfa"]
    assert _found(client, "ormaliz") == []


def test_search_all_terms_required_any_order(app, client, user):
    s = _subject("Redes")
    _material(user, s, "Alfa", "forma normal")
    _material(user, s, "Beta", "solo forma")
    assert _found(client, "normal forma") == ["Alfa"]


def test_search_quoted_phrase(app, client, user):
    s = _subject("Redes")
    _material(user, s, "Alfa", "forma normal")
    _material(user, s, "Beta", "normal forma")
    assert _found(client, "%22forma normal%22") == ["Alfa"]


def test_search_matches_subject_and_author_name(app, client, user):
    _material(user, _subject("Termodinámica"), "Alfa")
    assert _found(client, "termodinamica") == ["Alfa"]
    assert _found(client, "garcia") == ["Alfa"]


def test_search_relevance_default_with_q_only(app, client, user):
    s = _subject("Redes")
    # La coincidencia en el título (Beta) no es ni la más antigua ni la más nueva ni la de mayor id.
    _material(user, s, "Alfa", "sobre grafos", minutes=0)
    _material(user, s, "Beta grafos", "nada", minutes=1)
    _material(user, s, "Gamma", "sobre grafos", minutes=2)
    assert "Más relevantes" not in client.get("/explorar").get_data(as_text=True)
    with_q = client.get("/explorar?q=grafos").get_data(as_text=True)
    assert "Más relevantes" in with_q
    assert with_q.index("Beta grafos") < with_q.index(">Gamma<")
    assert with_q.index("Beta grafos") < with_q.index(">Alfa<")
    recent = client.get("/explorar?q=grafos&orden=recientes").get_data(as_text=True)
    assert recent.index(">Gamma<") < recent.index("Beta grafos") < recent.index(">Alfa<")


def test_title_match_outranks_description_match(app, client, user):
    s = _subject("Redes")
    _material(user, s, "Alfa", "grafos", minutes=0)
    _material(user, s, "Beta grafos", "otra cosa", minutes=1)
    _material(user, s, "Gamma", "grafos", minutes=2)
    html = client.get("/explorar?q=grafos").get_data(as_text=True)
    assert html.index("Beta grafos") < html.index(">Alfa<")
    assert html.index("Beta grafos") < html.index(">Gamma<")


def test_relevance_without_valid_terms_ignores_q(app, client, user):
    _material(user, _subject("Redes"), "Alfa")
    assert _found(client, "!!!") == ["Alfa"]
    assert _found(client, "x", "&orden=relevantes") == []
    html = client.get("/explorar?orden=relevantes").get_data(as_text=True)
    assert ">Alfa<" in html and "Más relevantes" not in html


def test_relevance_option_hidden_when_q_has_no_valid_terms(app, client, user):
    _material(user, _subject("Redes"), "Alfa")
    html = client.get("/explorar?q=!!!").get_data(as_text=True)
    assert ">Alfa<" in html and "Más relevantes" not in html
    assert "Más relevantes" in client.get("/explorar?q=alfa").get_data(as_text=True)


def test_search_combines_with_filters_and_excludes_hidden(app, client, user):
    s1, s2 = _subject("Redes"), _subject("Bases")
    _material(user, s1, "Alfa", "grafos")
    _material(user, s2, "Beta", "grafos")
    _material(user, s1, "Gamma", "grafos", is_hidden=True)
    assert _found(client, "grafos") == ["Alfa", "Beta"]
    assert _found(client, "grafos", f"&asignatura={s1.id}") == ["Alfa"]
    assert _found(client, "grafos", "&orden=valorados") == ["Alfa", "Beta"]


def test_index_follows_edit_delete_subject_rename_user_rename(app, client, user):
    subject = _subject("Redes")
    material = _material(user, subject, "Alfa", "grafos")
    assert _found(client, "grafos") == ["Alfa"]
    material.description = "arboles"
    db.session.commit()
    assert _found(client, "grafos") == [] and _found(client, "arboles") == ["Alfa"]
    subject.name = "Criptografía"
    db.session.commit()
    assert _found(client, "criptografia") == ["Alfa"] and _found(client, "redes") == []
    user.surname = "Lovelace"
    db.session.commit()
    assert _found(client, "lovelace") == ["Alfa"] and _found(client, "garcia") == []
    db.session.delete(material)
    db.session.commit()
    assert _fts_ids() == []


def test_index_follows_subject_change_and_hidden_toggle(app, client, user):
    old, new = _subject("Redes"), _subject("Criptografía")
    material = _material(user, old, "Alfa")
    material.subject_id = new.id
    db.session.commit()
    assert _found(client, "criptografia") == ["Alfa"] and _found(client, "redes") == []
    material.is_hidden = True
    db.session.commit()
    assert _found(client, "criptografia") == []
    material.is_hidden = False
    db.session.commit()
    assert _found(client, "criptografia") == ["Alfa"]


def test_rollback_leaves_index_consistent(app, user):
    subject = _subject("Redes")
    material = _material(user, subject, "Alfa")
    material_id = material.id
    db.session.add(Material(title="Beta", description="", subject_id=subject.id, author_id=user.id))
    db.session.flush()
    assert len(_fts_ids()) == 2
    db.session.rollback()
    assert _fts_ids() == [material_id]


@pytest.mark.parametrize("q", ['"', '*', 'NEAR(', 'AND OR NOT', '-x', '^a', '!!!', '😀', 'a' * 5000, 'x\x00y',
                               '"a" "b', '( ) :'])
def test_malicious_queries_never_500(app, client, user, q):
    _material(user, _subject("Redes"), "Alfa", "secreto", is_hidden=True)
    _material(user, _subject("Bases"), "Beta")
    response = client.get("/explorar", query_string={"q": q})
    assert response.status_code == 200
    assert ">Alfa<" not in response.get_data(as_text=True)


def test_nul_byte_raw_url(app, client, user):
    assert client.get("/explorar?q=x%00y").status_code == 200


def test_build_match():
    assert build_match("Hola mundo") == '"Hola"* "mundo"*'
    assert build_match('"forma normal" x') == '"forma normal" "x"*'
    assert build_match("AND or Near not") is None
    assert build_match("  ") is None and build_match("😀 !!!") is None
    assert build_match("a-b (c)") == '"ab"* "c"*'


def test_build_match_caps_10_terms():
    match = build_match(" ".join(f"t{i}" for i in range(30)))
    assert len(match.split()) == 10


def test_reindex_command(app, user):
    from website.commands import reindex_search_command
    _material(user, _subject("Redes"), "Alfa")
    db.session.execute(text("DELETE FROM material_fts"))
    db.session.commit()
    result = CliRunner().invoke(reindex_search_command)
    assert result.exit_code == 0 and "1" in result.output
    assert len(_fts_ids()) == 1


def test_fts5_missing_raises_clear_error(monkeypatch):
    class Broken:
        def execute(self, *_):
            raise sqlite3.OperationalError("no such module: fts5")

        def close(self):
            pass

    monkeypatch.setattr(search.sqlite3, "connect", lambda *_a, **_k: Broken())
    with pytest.raises(RuntimeError, match="Esta instalación de SQLite no incluye FTS5"):
        search.check_fts5_available()
    with pytest.raises(RuntimeError, match="FTS5"):
        create_app({"TESTING": True, "SECRET_KEY": "k", "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
