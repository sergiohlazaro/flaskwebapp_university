"""Portada y páginas públicas."""

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

main = Blueprint("main", __name__)


@main.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("materials.explore"))
    return render_template("main/landing.html")


@main.route("/sobre")
def about():
    return render_template("main/about.html")


@main.route("/contacto")
def contact():
    return render_template("main/contact.html")


@main.route("/aviso-legal")
def legal():
    return render_template("main/legal.html")


@main.route("/privacidad")
def privacy():
    return render_template("main/privacy.html")


@main.route("/cookies")
def cookies():
    return render_template("main/cookies.html")


# URLs antiguas -> nuevas (301)
for _old, _endpoint in [("/about", "main.about"), ("/contact", "main.contact"),
                        ("/legal", "main.legal"), ("/privacy", "main.privacy")]:
    main.add_url_rule(
        _old, endpoint=f"old_{_old[1:]}",
        view_func=lambda e=_endpoint: redirect(url_for(e), 301),
    )
