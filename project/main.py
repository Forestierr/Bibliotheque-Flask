# main.py
import os

from flask import (
    Blueprint,
    render_template,
    request,
    url_for,
    send_from_directory,
    flash,
    redirect,
    send_file,
    jsonify,
)
from flask_login import login_required, current_user
from werkzeug.exceptions import HTTPException

from .email import send_email_to_me, send_email_confirmation
from .query import (
    get_app_infos,
    get_books_count,
    get_students_count,
    get_books_most_borrowed,
    get_students_most_borrowed,
    get_last_book_loan,
    get_loans_over_the_year,
    get_user,
    get_books_read_by_students,
)

main = Blueprint("main", __name__)


@main.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    infos = get_app_infos()

    return render_template("index.html", infos=infos)


@main.route("/dashboard")
@login_required
def dashboard():
    n_books = get_books_count(current_user.id)
    n_students = get_students_count(current_user.id)

    # get the 5 books most borrowed
    books = get_books_most_borrowed(current_user.id)

    # get the 5 students who borrowed the most
    students = get_students_most_borrowed(current_user.id)

    # get the 5 list books loaned or returned
    books_loaned = get_last_book_loan(current_user.id)

    # get the loan and returns of each day for the last 365 days (max 371 day)
    loans = get_loans_over_the_year(current_user.id)

    # Calculate month spans based on the weeks in `loans`.
    # A contribution graph has columns representing weeks.
    months = []
    if loans:
        current_month_str = ""
        current_span = 0
        for w in range(0, len(loans), 7):
            # We take the first day of the week to determine the month of this column
            month_str = loans[w][0].strftime("%b")

            if month_str == current_month_str:
                current_span += 1
            else:
                if current_month_str != "":
                    months.append((current_month_str, current_span))
                current_month_str = month_str
                current_span = 1

        if current_month_str != "":
            months.append((current_month_str, current_span))

    return render_template(
        "user/dashboard.html",
        n_books=n_books,
        n_students=n_students,
        books=books,
        students=students,
        books_loaned=books_loaned,
        months=months,
        loans=loans,
    )


@main.route("/sitemap.xml")
@main.route("/sitemap")
def sitemap():
    return render_template("utils/sitemap.xml")


@main.route("/robots.txt")
@main.route("/robot.txt")
@main.route("/robots")
@main.route("/robot")
def robots():
    return render_template("utils/robots.txt")


@main.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(main.root_path, "static/image"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


@main.route("/contact", methods=["GET", "POST"])
@login_required
def contact():
    if request.method == "POST":
        name = request.form.get("name")
        firstname = request.form.get("firstname")
        email = request.form.get("email")
        message = request.form.get("message")

        if not name or not firstname or not email or not message:
            flash("Veuillez remplir tous les champs.", "danger")
            return redirect(url_for("main.contact"))

        # envoi d'un email à l'administrateur
        send_email_to_me(
            "Contact de " + name + " " + firstname,
            "Email: "
            + email
            + "\n"
            + "Nom: "
            + name
            + " "
            + firstname
            + "\n\n"
            + message,
        )

        # envoi d'un email de confirmation à l'utilisateur
        send_email_confirmation(name, firstname, email)

        flash(
            "Votre message a été envoyé avec succès. Vous avez reçu un email de confirmation.",
            "success",
        )

        return redirect(url_for("main.contact"))

    user = get_user(current_user.id)

    return render_template("contact.html", user=user)


@main.route("/mentions_legales")
def mentions_legales():
    return render_template("mentions-legales.html")


@main.route("/apropos")
@main.route("/about")
def apropos():
    return render_template("apropos.html")


# SEO Dynamic Routes
@main.route("/blog")
def blog_index():
    return render_template("blog/index.html")


@main.route("/blog/<path:article_slug>")
def blog_article(article_slug):
    try:
        return render_template(f"blog/{article_slug}.html")
    except Exception:
        return render_template("error.html", error="Article non trouvé"), 404


@main.route("/ressources")
def ressources_index():
    return render_template("ressources/index.html")


@main.route("/ressources/<path:ressource_slug>")
def ressource_article(ressource_slug):
    try:
        return render_template(f"ressources/{ressource_slug}.html")
    except Exception:
        return render_template("error.html", error="Ressource non trouvée"), 404


@main.route("/enseignants")
def enseignants_index():
    return render_template("enseignants/index.html")


@main.route("/enseignants/<path:guide_slug>")
def enseignants_guide(guide_slug):
    try:
        return render_template(f"enseignants/{guide_slug}.html")
    except Exception:
        return render_template("error.html", error="Guide non trouvé"), 404


@main.route("/install")
def install():
    return render_template("utils/app_install.html")


# Error handling
@main.app_errorhandler(HTTPException)
def page_not_found(e):
    return render_template("error.html", error=e), e.code


# PWA code
@main.route("/manifest.json")
def serve_manifest():
    return send_file("manifest.json", mimetype="application/manifest+json")


@main.route("/sw.js")
def serve_sw():
    return send_file("static/javascript/sw.js", mimetype="application/javascript")


@main.route("/api/student_books_read")
@login_required
def api_student_books_read():
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    if not date_from or not date_to:
        return jsonify({"labels": [], "data": []})
    results = get_books_read_by_students(current_user.id, date_from, date_to)
    labels = [r[0] for r in results]
    data = [r[1] for r in results]
    return jsonify({"labels": labels, "data": data})
