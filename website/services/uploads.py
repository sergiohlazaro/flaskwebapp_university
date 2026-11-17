"""Almacenamiento privado de ficheros subidos (fuera de static/).

Los ficheros se guardan en UPLOAD_ROOT/<kind>/ con un nombre aleatorio; el nombre
original (controlado por el usuario) solo se conserva, saneado, como metadato.
"""
import mimetypes
import os
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Literal

from flask import current_app
from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

Kind = Literal["materials", "messages", "avatars"]
KINDS = ("materials", "messages", "avatars")

ALLOWED_MATERIAL_EXTENSIONS = frozenset({
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    "odt", "odp", "txt", "md", "zip", "png", "jpg", "jpeg", "gif",
})
ALLOWED_IMAGE_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "gif"})

_ZIP_EXTS = frozenset({"docx", "pptx", "xlsx", "odt", "odp", "zip"})
_OLE_EXTS = frozenset({"doc", "ppt", "xls"})
_TEXT_EXTS = frozenset({"txt", "md"})
_ZIP_MAGIC = b"PK\x03\x04"
_OLE_MAGIC = b"\xd0\xcf\x11\xe0"
_NAME_MAX = 255  # tamaño de las columnas original_name / file_original_name
_IMAGE_MIMES = {"png": "image/png", "jpeg": "image/jpeg", "gif": "image/gif"}
_IMAGE_STORED_EXT = {"png": "png", "jpeg": "jpg", "gif": "gif"}


class UploadError(ValueError):
    """Error de validación de una subida; el mensaje (en español) se muestra al usuario."""


@dataclass(frozen=True)
class SavedFile:
    stored_name: str
    original_name: str
    mime: str
    size: int


def detect_image_type(stream):
    """Tipo real de una imagen a partir de su contenido ('png', 'jpeg', 'gif'...).

    Devuelve None si no es una imagen. Pillow identifica como MPO los JPEG
    multi-imagen de muchos móviles: se tratan como jpeg.
    """
    try:
        with Image.open(stream) as image:
            image.verify()
            detected = (image.format or "").lower() or None
            return "jpeg" if detected == "mpo" else detected
    except Image.DecompressionBombError:
        raise UploadError("La imagen es demasiado grande.") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        return None
    finally:
        stream.seek(0)


def clean_original_name(name: str | None, max_len: int = _NAME_MAX) -> str:
    """Sanea un nombre de fichero del usuario: sin rutas ni caracteres de control,
    conservando Unicode, y recortado a max_len sin perder la extensión."""
    name = unicodedata.normalize("NFC", name or "")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in name if unicodedata.category(c) not in ("Cc", "Zl", "Zp")).strip()
    name = name.lstrip(".") or "archivo"
    if len(name) > max_len:
        stem, ext = os.path.splitext(name)
        ext = ext[:20]
        name = stem[: max_len - len(ext)] + ext
    return name


def _extension(filename: str | None) -> str:
    name = clean_original_name(filename)
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def validate_upload(file: FileStorage, allowed: frozenset[str]) -> str:
    """Valida extensión y firma del contenido. Devuelve la extensión normalizada."""
    if file is None or not file.filename:
        raise UploadError("No se ha seleccionado ningún archivo.")
    ext = _extension(file.filename)
    if ext not in allowed:
        raise UploadError("Tipo de archivo no permitido.")
    stream = file.stream
    stream.seek(0)
    try:
        if ext in ALLOWED_IMAGE_EXTENSIONS:
            detected = detect_image_type(stream)
            if detected not in _IMAGE_STORED_EXT or _IMAGE_STORED_EXT[detected] != (
                "jpg" if ext == "jpeg" else ext
            ):
                raise UploadError("El archivo no es una imagen válida.")
        elif ext == "pdf":
            if stream.read(5) != b"%PDF-":
                raise UploadError("El archivo no es un PDF válido.")
        elif ext in _ZIP_EXTS:
            if stream.read(4) != _ZIP_MAGIC:
                raise UploadError("El contenido del archivo no coincide con su extensión.")
        elif ext in _OLE_EXTS:
            if stream.read(4) != _OLE_MAGIC:
                raise UploadError("El contenido del archivo no coincide con su extensión.")
        elif ext in _TEXT_EXTS:
            try:
                text = stream.read().decode("utf-8").lower()
            except UnicodeDecodeError:
                raise UploadError("El archivo de texto no es válido.") from None
            if "<script" in text or "<html" in text:
                raise UploadError("El archivo de texto contiene código no permitido.")
    finally:
        stream.seek(0)
    return ext


def _kind_dir(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"Tipo de subida desconocido: {kind}")
    return os.path.join(current_app.config["UPLOAD_ROOT"], kind)


def upload_path(kind: str, stored_name: str) -> str:
    if not stored_name or stored_name != os.path.basename(stored_name) or stored_name in (".", ".."):
        raise ValueError("Nombre de fichero almacenado no válido")
    return os.path.join(_kind_dir(kind), stored_name)


def _new_stored_name(ext: str) -> str:
    return f"{uuid.uuid4().hex}.{ext}"


def save_upload(file: FileStorage, kind: Kind, allowed: frozenset[str]) -> SavedFile:
    ext = validate_upload(file, allowed)
    os.makedirs(_kind_dir(kind), exist_ok=True)
    stored_name = _new_stored_name("jpg" if ext == "jpeg" else ext)
    path = upload_path(kind, stored_name)
    file.stream.seek(0)
    file.save(path)
    mime = mimetypes.guess_type(f"x.{ext}")[0] or "application/octet-stream"
    return SavedFile(stored_name, clean_original_name(file.filename), mime, os.path.getsize(path))


def save_avatar(file: FileStorage) -> SavedFile:
    """Valida con Pillow (MPO→JPEG), redimensiona a 300x300 como máximo y guarda."""
    validate_upload(file, ALLOWED_IMAGE_EXTENSIONS)
    detected = detect_image_type(file.stream)  # validate_upload ya lo comprobó
    fmt = {"png": "PNG", "jpeg": "JPEG", "gif": "GIF"}.get(detected)
    if fmt is None:
        raise UploadError("El archivo no es una imagen válida.")
    os.makedirs(_kind_dir("avatars"), exist_ok=True)
    stored_name = _new_stored_name(_IMAGE_STORED_EXT[detected])
    path = upload_path("avatars", stored_name)
    try:
        with Image.open(file.stream) as image:
            image.thumbnail((300, 300))
            if fmt == "JPEG" and image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            image.save(path, format=fmt)
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        if os.path.exists(path):
            os.remove(path)
        raise UploadError("El archivo no es una imagen válida.") from None
    return SavedFile(stored_name, clean_original_name(file.filename), _IMAGE_MIMES[detected],
                     os.path.getsize(path))


def delete_upload(kind: str, stored_name: str) -> None:
    """Borra un fichero subido; no falla si no existe o el nombre no es válido."""
    try:
        os.remove(upload_path(kind, stored_name))
    except (FileNotFoundError, ValueError):
        pass
