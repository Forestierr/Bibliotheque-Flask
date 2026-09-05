import os
from datetime import datetime, timezone
from threading import Thread

import jinja2
from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from flask_mail import Message
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from . import db
from .email import send_email_async, send_email_confirmation, send_email_to_me
from .models import Feedback, NewsletterDelivery
from .query import (
    get_app_infos,
    get_books_count,
    get_books_most_borrowed,
    get_books_read_by_students,
    get_last_book_loan,
    get_loans_over_the_year,
    get_students_count,
    get_students_most_borrowed,
    get_user,
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


@main.route("/llms.txt")
@main.route("/llms")
def llms():
    return render_template("utils/llms.txt")


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


def send_feedback_notification(user, feedback_obj):
    admin_email = os.getenv("MAIL_USERNAME")
    if not admin_email:
        return

    category_labels = {
        "suggestion": "Suggestion d'amélioration",
        "bug": "Signalement de bug",
        "general": "Avis général",
    }
    cat_label = category_labels.get(feedback_obj.category, feedback_obj.category)

    subject = f"[Retour - {cat_label}] {feedback_obj.subject}"
    body = (
        f"Nouveau retour utilisateur sur LivresEnClasse :\n\n"
        f"Auteur : {user.name or 'Non renseigné'} ({user.email})\n"
        f"ID Utilisateur : {user.id}\n"
        f"Type : {cat_label}\n"
        f"Sujet : {feedback_obj.subject}\n"
        f"Page indiquée : {feedback_obj.page_url or 'Non spécifiée'}\n"
        f"Navigateur : {feedback_obj.user_agent or 'Non spécifié'}\n"
        f"Date : {feedback_obj.created_at.strftime('%d/%m/%Y à %H:%M')}\n\n"
        f"Message :\n{feedback_obj.message}\n\n"
        f"---\n"
        f"Vous pouvez répondre directement à cet email pour échanger avec l'utilisateur."
    )

    app = current_app._get_current_object()
    msg = Message(
        subject,
        sender=admin_email,
        recipients=[admin_email],
        reply_to=user.email,
    )
    msg.body = body
    thr = Thread(target=send_email_async, args=[app, msg])
    thr.start()


@main.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    if request.method == "POST":
        category = request.form.get("category", "suggestion").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        page_url = request.form.get("page_url", "").strip()

        if not subject or not message:
            flash(
                "Veuillez renseigner l'objet et la description de votre retour.",
                "danger",
            )
            return redirect(url_for("main.feedback", type=category))

        valid_categories = {"suggestion", "bug", "general"}
        if category not in valid_categories:
            category = "suggestion"

        user_agent_str = request.user_agent.string if request.user_agent else None
        if user_agent_str and len(user_agent_str) > 255:
            user_agent_str = user_agent_str[:255]

        new_feedback = Feedback(
            user_id=current_user.id,
            category=category,
            subject=subject[:200],
            message=message,
            page_url=page_url[:255] if page_url else None,
            user_agent=user_agent_str,
            status="nouveau",
        )
        db.session.add(new_feedback)
        db.session.commit()

        # Envoi de la notification par courriel à l'administrateur
        try:
            send_feedback_notification(current_user, new_feedback)
        except Exception:
            current_app.logger.exception(
                "Erreur lors de l'envoi de la notification de feedback"
            )

        flash(
            "Votre retour a été transmis avec succès. Merci pour votre aide précieuse !",
            "success",
        )
        return redirect(url_for("main.feedback"))

    initial_type = request.args.get("type", "suggestion")
    initial_url = request.args.get("url", "")
    return render_template(
        "feedback.html",
        initial_type=initial_type,
        initial_url=initial_url,
    )


@main.route("/mentions_legales")
def mentions_legales():
    return render_template("mentions-legales.html")


@main.route("/apropos")
@main.route("/about")
def apropos():
    return render_template("apropos.html")


@main.route("/aide")
@main.route("/help")
@login_required
def aide():
    return render_template("aide.html")


# SEO Dynamic Routes
@main.route("/blog")
def blog_index():
    return render_template("blog/index.html")


@main.route("/blog/<path:article_slug>")
def blog_article(article_slug):
    try:
        return render_template(f"blog/{article_slug}.html")
    except jinja2.TemplateNotFound:
        return render_template("error.html", error="Article non trouvé"), 404


@main.route("/ressources")
def ressources_index():
    return render_template("ressources/index.html")


@main.route("/ressources/<path:ressource_slug>")
def ressource_article(ressource_slug):
    try:
        return render_template(f"ressources/{ressource_slug}.html")
    except jinja2.TemplateNotFound:
        return render_template("error.html", error="Ressource non trouvée"), 404


@main.route("/enseignants")
def enseignants_index():
    return render_template("enseignants/index.html")


@main.route("/enseignants/<path:guide_slug>")
def enseignants_guide(guide_slug):
    try:
        return render_template(f"enseignants/{guide_slug}.html")
    except jinja2.TemplateNotFound:
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


# 1x1 transparent PNG pixel for email open tracking
TRACKING_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00"
    b"\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
)


@main.route("/email/track/<token>.png", methods=["GET", "HEAD"])
@main.route("/email/track/<token>", methods=["GET", "HEAD"])
def email_track(token):
    delivery = NewsletterDelivery.query.filter_by(tracking_token=token).first()
    if delivery:
        now = datetime.now(timezone.utc)
        if delivery.opened_at is None:
            delivery.opened_at = now
            if delivery.campaign:
                delivery.campaign.open_count = (delivery.campaign.open_count or 0) + 1
        delivery.open_count = (delivery.open_count or 0) + 1
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()

    response = Response(TRACKING_PIXEL_PNG, mimetype="image/png")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
