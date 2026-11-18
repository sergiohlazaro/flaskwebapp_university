"""Utilidades compartidas de consulta (website/services/query.py)."""
from website.services.query import MAX_INT, MAX_PAGE, escape_like, int_param, page_param


def test_escape_like_escapes_wildcards():
    assert escape_like(r"50%_a\b") == r"50\%\_a\\b"


def test_int_param_is_bounded():
    assert int_param("5") == 5
    assert int_param("0") is None
    assert int_param("0", minimum=0) == 0
    assert int_param(str(MAX_INT)) == MAX_INT
    assert int_param(str(MAX_INT + 1)) is None
    assert int_param("x") is None
    assert int_param(None) is None


def test_page_param_defaults_and_caps():
    assert page_param(None) == 1
    assert page_param("-3") == 1
    assert page_param(str(MAX_PAGE + 5)) == MAX_PAGE
    assert page_param("7") == 7

