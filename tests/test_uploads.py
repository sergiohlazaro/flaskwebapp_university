import io
import os
import re

import pytest
from conftest import png_bytes
from werkzeug.datastructures import FileStorage

from website.services.uploads import (
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_MATERIAL_EXTENSIONS,
    UploadError,
    save_avatar,
    save_upload,
    upload_path,
    validate_upload,
)


def fs(data, name):
    if isinstance(data, bytes):
        data = io.BytesIO(data)
    return FileStorage(stream=data, filename=name)


def test_allowed_extension_sets():
    assert ALLOWED_MATERIAL_EXTENSIONS == frozenset({
        "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
        "odt", "odp", "txt", "md", "zip", "png", "jpg", "jpeg", "gif",
    })
    assert ALLOWED_IMAGE_EXTENSIONS == frozenset({"png", "jpg", "jpeg", "gif"})


def test_rejects_html_renamed_as_pdf(app):
    with pytest.raises(UploadError):
        validate_upload(fs(b"<html><script>x</script></html>", "a.pdf"), ALLOWED_MATERIAL_EXTENSIONS)


def test_rejects_text_renamed_as_png(app):
    with pytest.raises(UploadError):
        validate_upload(fs(b"hola mundo", "a.png"), ALLOWED_MATERIAL_EXTENSIONS)


def test_rejects_html_renamed_as_txt(app):
    with pytest.raises(UploadError):
        validate_upload(fs(b"<HTML>hi", "a.txt"), ALLOWED_MATERIAL_EXTENSIONS)


def test_accepts_uppercase_extension(app):
    assert validate_upload(fs(b"%PDF-1.4 x", "APUNTES.PDF"), ALLOWED_MATERIAL_EXTENSIONS) == "pdf"


def test_signatures_for_office_and_zip(app):
    assert validate_upload(fs(b"PK\x03\x04rest", "a.docx"), ALLOWED_MATERIAL_EXTENSIONS) == "docx"
    assert validate_upload(fs(b"\xd0\xcf\x11\xe0rest", "a.xls"), ALLOWED_MATERIAL_EXTENSIONS) == "xls"
    with pytest.raises(UploadError):
        validate_upload(fs(b"%PDF-", "a.zip"), ALLOWED_MATERIAL_EXTENSIONS)


def test_rejects_disallowed_extension(app):
    with pytest.raises(UploadError):
        validate_upload(fs(b"MZ", "virus.exe"), ALLOWED_MATERIAL_EXTENSIONS)
    with pytest.raises(UploadError):
        validate_upload(fs(b"%PDF-", "sinextension"), ALLOWED_MATERIAL_EXTENSIONS)


def test_rejects_extension_outside_given_allowed_set(app):
    with pytest.raises(UploadError):
        validate_upload(fs(b"%PDF-", "a.pdf"), ALLOWED_IMAGE_EXTENSIONS)


def test_error_messages_are_spanish(app):
    with pytest.raises(UploadError, match="(?i)archivo|fichero|extensi"):
        validate_upload(fs(b"MZ", "virus.exe"), ALLOWED_MATERIAL_EXTENSIONS)


def test_saved_name_is_random_and_keeps_extension(app):
    saved = save_upload(fs(b"%PDF-1.4 x", "Notas.PDF"), "materials", ALLOWED_MATERIAL_EXTENSIONS)
    assert re.fullmatch(r"[0-9a-f]{32}\.pdf", saved.stored_name)
    assert saved.original_name == "Notas.PDF"
    assert saved.mime == "application/pdf"
    assert saved.size == len(b"%PDF-1.4 x")
    assert os.path.exists(upload_path("materials", saved.stored_name))


def test_same_original_name_never_overwrites(app):
    a = save_upload(fs(b"%PDF-AAA", "notas.pdf"), "materials", ALLOWED_MATERIAL_EXTENSIONS)
    b = save_upload(fs(b"%PDF-BBB", "notas.pdf"), "materials", ALLOWED_MATERIAL_EXTENSIONS)
    assert a.stored_name != b.stored_name
    with open(upload_path("materials", a.stored_name), "rb") as f:
        assert f.read() == b"%PDF-AAA"
    with open(upload_path("materials", b.stored_name), "rb") as f:
        assert f.read() == b"%PDF-BBB"


def test_long_original_name_is_capped(app):
    name = "a" * 200 + ".pdf"
    saved = save_upload(fs(b"%PDF-1", name), "materials", ALLOWED_MATERIAL_EXTENSIONS)
    assert len(saved.original_name) <= 255
    assert saved.original_name.endswith(".pdf")
    huge = save_upload(fs(b"%PDF-1", "b" * 400 + ".pdf"), "materials", ALLOWED_MATERIAL_EXTENSIONS)
    assert len(huge.original_name) <= 255 and huge.original_name.endswith(".pdf")


def test_original_name_strips_paths_and_control_chars(app):
    saved = save_upload(fs(b"%PDF-1", "..\\..\\etc/pa\x00s\nswd.pdf"), "materials", ALLOWED_MATERIAL_EXTENSIONS)
    assert "/" not in saved.original_name and "\\" not in saved.original_name
    assert not any(ord(c) < 32 for c in saved.original_name)


def test_delete_upload_is_idempotent(app):
    from website.services.uploads import delete_upload
    saved = save_upload(fs(b"%PDF-1", "a.pdf"), "materials", ALLOWED_MATERIAL_EXTENSIONS)
    delete_upload("materials", saved.stored_name)
    assert not os.path.exists(upload_path("materials", saved.stored_name))
    delete_upload("materials", saved.stored_name)
    delete_upload("materials", "../../etc/passwd")


def test_save_avatar_resizes_and_rejects_fakes(app):
    from PIL import Image
    saved = save_avatar(fs(png_bytes(size=(800, 600)), "me.png"))
    with Image.open(upload_path("avatars", saved.stored_name)) as im:
        assert max(im.size) <= 300
    with pytest.raises(UploadError):
        save_avatar(fs(b"<script>alert(1)</script>", "evil.png"))


def test_files_live_outside_static(app):
    path = upload_path("materials", "abc.pdf")
    assert path.startswith(app.config["UPLOAD_ROOT"])
    assert not path.startswith(os.path.join(app.root_path, "static"))


def _bmp_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="BMP")
    return buf.getvalue()


def test_real_bmp_renamed_png_is_upload_error(app):
    with pytest.raises(UploadError):
        validate_upload(fs(_bmp_bytes(), "a.png"), ALLOWED_MATERIAL_EXTENSIONS)
    with pytest.raises(UploadError):
        save_avatar(fs(_bmp_bytes(), "a.png"))


def test_real_webp_renamed_jpg_is_upload_error(app):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="WEBP")
    with pytest.raises(UploadError):
        validate_upload(fs(buf.getvalue(), "a.jpg"), ALLOWED_MATERIAL_EXTENSIONS)


def test_decompression_bomb_is_upload_error(app, monkeypatch):
    from PIL import Image
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)
    with pytest.raises(UploadError, match="demasiado grande"):
        validate_upload(fs(png_bytes(size=(10, 10)), "a.png"), ALLOWED_MATERIAL_EXTENSIONS)
    with pytest.raises(UploadError, match="demasiado grande"):
        save_avatar(fs(png_bytes(size=(10, 10)), "a.png"))
