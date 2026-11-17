import pytest
from conftest import make_user
from sqlalchemy.exc import IntegrityError

from website import db
from website.models import (
    Comment,
    Course,
    Favorite,
    Material,
    MaterialFile,
    MaterialKind,
    Message,
    Rating,
    Subject,
)


def _material(author, subject=None):
    subject = subject or Subject(name="Cálculo")
    material = Material(title="Apuntes tema 1", subject=subject, author_id=author.id,
                        course=Course.FIRST, kind=MaterialKind.NOTES)
    db.session.add(material)
    db.session.commit()
    return material


def test_rating_rejects_out_of_range(app):
    user = make_user("a@example.com")
    material = _material(user)
    db.session.add(Rating(user_id=user.id, material_id=material.id, stars=6))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_one_rating_per_user_and_material(app):
    user = make_user("a@example.com")
    material = _material(user)
    db.session.add(Rating(user_id=user.id, material_id=material.id, stars=3))
    db.session.commit()
    db.session.add(Rating(user_id=user.id, material_id=material.id, stars=4))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_deleting_material_cascades(app):
    user = make_user("a@example.com")
    material = _material(user)
    db.session.add_all([
        MaterialFile(material_id=material.id, stored_name="x.pdf", original_name="x.pdf",
                     mime="application/pdf", size=10),
        Rating(user_id=user.id, material_id=material.id, stars=5),
        Favorite(user_id=user.id, material_id=material.id),
        Comment(material_id=material.id, author_id=user.id, body="hola"),
    ])
    db.session.commit()
    db.session.delete(db.session.get(Material, material.id))
    db.session.commit()
    for model in (MaterialFile, Rating, Favorite, Comment):
        assert model.query.count() == 0


def test_average_rating_and_count(app):
    a = make_user("a@example.com")
    b = make_user("b@example.com")
    material = _material(a)
    assert material.average_rating is None
    assert material.rating_count == 0
    db.session.add_all([
        Rating(user_id=a.id, material_id=material.id, stars=4),
        Rating(user_id=b.id, material_id=material.id, stars=5),
    ])
    db.session.commit()
    db.session.refresh(material)
    assert material.average_rating == 4.5
    assert material.rating_count == 2


def test_message_survives_sender_deletion(app):
    sender = make_user("s@example.com")
    receiver = make_user("r@example.com")
    message = Message(sender_id=sender.id, receiver_id=receiver.id, content="hola")
    db.session.add(message)
    db.session.commit()
    message_id = message.id
    db.session.delete(sender)
    db.session.commit()
    db.session.expire_all()
    survivor = db.session.get(Message, message_id)
    assert survivor is not None
    assert survivor.sender_id is None


def test_subject_name_unique_case_insensitive(app):
    db.session.add(Subject(name="Cálculo"))
    db.session.commit()
    db.session.add(Subject(name="cálculo"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
