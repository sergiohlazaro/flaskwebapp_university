from flask import Blueprint, redirect, url_for
from flask_login import login_required

# Blueprint con las rutas antiguas que solo redirigen a las nuevas
views = Blueprint('views', __name__)

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

@views.route('/messages')
def messages_redirect():
    return redirect(url_for("messages.inbox"), code=301)
