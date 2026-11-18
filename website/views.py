# ---------------------------------
# IMPORTACIONES
# ---------------------------------
import os  # Librería para operaciones con archivos y carpetas
import uuid  # Nombres de fichero únicos para las subidas
from werkzeug.utils import secure_filename  # Asegura que los nombres de archivos sean seguros para guardarlos
from flask import Blueprint, redirect, render_template, url_for, request, flash
from flask_login import login_required, current_user  # Gestión de sesiones de usuarios


# Modelos de base de datos
from .models import db, User, Message

# Consultas avanzadas de SQLAlchemy
from sqlalchemy import or_, and_

# Sanitización de entradas para evitar ataques XSS
import bleach

# Para logging de eventos
import logging

# Importación del limitador de solicitudes (Rate Limiting) para prevenir ataques de fuerza bruta
from .extensions import limiter

# ---------------------------------
# CONFIGURACIONES
# ---------------------------------

# Creación del blueprint para agrupar todas las rutas de "views"
views = Blueprint('views', __name__)

# Extensiones permitidas para archivos de publicaciones/mensajes
ALLOWED_EXTENSIONS_DOCS = {'pdf', 'doc', 'docx', 'txt', 'png', 'jpg', 'jpeg', 'gif'}

# ---------------------------------
# FUNCIONES DE UTILIDAD
# ---------------------------------

# Verifica si un archivo tiene una extensión válida para archivos en general
def allowed_file_generic(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS_DOCS

# Genera un nombre de fichero único para guardar en disco, conservando solo la
# extensión del original. Evita que un usuario sobrescriba ficheros de otros
# (incluida la imagen de perfil por defecto compartida).
def unique_filename(original_name):
    ext = secure_filename(original_name).rsplit('.', 1)[-1].lower()
    return f"{uuid.uuid4().hex}.{ext}"

# ---------------------------------
# RUTAS PRINCIPALES (HOME, ABOUT, CONTACT)
# ---------------------------------

@views.route('/home')
@login_required
def home():
    """URL antigua: el feed vive ahora en /explorar."""
    return redirect(url_for("materials.explore"))

# ---------------------------------
# URLS ANTIGUAS (redirecciones permanentes)
# ---------------------------------

@views.route('/profile')
def profile_redirect():
    return redirect(url_for("users.account"), code=301)


@views.route('/userlist')
def userlist_redirect():
    return redirect(url_for("users.directory"), code=301)


@views.route('/publications')
def publications_redirect():
    return redirect(url_for("materials.explore"), code=301)

# ---------------------------------
# MENSAJES PRIVADOS ENTRE USUARIOS
# ---------------------------------

@views.route('/messages', methods=['GET'])
@login_required
def messages():
    """
    Muestra las conversaciones y permite seleccionar un usuario para ver los mensajes.
    """

    # Usuarios con los que se ha comunicado
    users_contacted = User.query.filter(
        User.id != current_user.id,
        or_(
            and_(Message.sender_id == current_user.id, Message.receiver_id == User.id),
            and_(Message.receiver_id == current_user.id, Message.sender_id == User.id)
        )
    ).distinct().all()

    selected_user_id = request.args.get('user_id', type=int)
    conversation = None

    if selected_user_id:
        conversation = Message.query.filter(
            or_(
                and_(Message.sender_id == current_user.id, Message.receiver_id == selected_user_id),
                and_(Message.receiver_id == current_user.id, Message.sender_id == selected_user_id)
            )
        ).order_by(Message.created_at).all()

    return render_template(
        'legacy/messages.html',
        user=current_user,
        users_contacted=users_contacted,
        conversation=conversation,
        selected_user_id=selected_user_id
    )

@views.route('/send_message', methods=['POST'])
@login_required
@limiter.limit("15 per hour")
def send_message():
    """
    Envía un mensaje privado a otro usuario. Permite adjuntar un archivo opcional.
    """
    receiver_email = request.form.get('receiver_email')
    content_raw = request.form.get('content')
    content = bleach.clean(content_raw)

    file = request.files.get('message_file')
    filename = None

    if not receiver_email or not content:
        flash('Receiver email and content are required', category='error')
        return redirect(url_for('views.messages'))

    receiver = User.query.filter_by(email=receiver_email).first()
    if not receiver:
        flash('User with this email does not exist!', category='error')
        return redirect(url_for('views.messages'))

    # Procesar archivo adjunto
    if file and allowed_file_generic(file.filename):
        # Verificar tipo MIME
        allowed_mimetypes = ["image/png", "image/jpeg", "image/gif", "application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"]
        if file.mimetype not in allowed_mimetypes:
            flash('Unsupported file MIME type.', category='error')
            return redirect(url_for('views.messages'))

        filename = unique_filename(file.filename)
        upload_folder = os.path.join('website', 'static', 'uploads', 'messages')
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)

    elif file and not allowed_file_generic(file.filename):
        flash('Unsupported file type.', category='error')
        return redirect(url_for('views.messages'))

    # Crear y guardar el mensaje
    new_message = Message(
        sender_id=current_user.id,
        receiver_id=receiver.id,
        content=content,
        file_stored_name=filename,
        file_original_name=file.filename if filename else None
    )
    db.session.add(new_message)
    db.session.commit()

    logging.info(f"User {current_user.email} sent a message to {receiver.email}")
    flash('Message sent', category='success')
    return redirect(url_for('views.messages'))
