# ressource.py

from flask import Blueprint, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user
from sqlalchemy import func

from . import db
from .models import Book, Loan, Student, Tags
from .subscription import premium_required

ressource = Blueprint("ressource", __name__)


@ressource.route("/ressources")
def index():
    """Catalogue principal des ressources pédagogiques et outils imprimables."""
    return render_template("ressources/index.html")


@ressource.route("/ressources/diplome-de-lecture-a-imprimer")
def diplome_de_lecture_a_imprimer():
    """Générateur de diplôme de lecture personnalisé."""
    student_id = request.args.get("student_id", type=int)
    student = None
    read_count = 0
    students_list = []

    if current_user.is_authenticated:
        raw_students = (
            Student.query.filter_by(user_id=current_user.id)
            .order_by(Student.name, Student.firstname)
            .all()
        )

        # Calculer le nombre de livres lus (retournés) par élève
        loan_counts_query = (
            db.session.query(Loan.student_id, func.count(Loan.id))
            .filter(Loan.date_return.isnot(None))
            .join(Student, Loan.student_id == Student.id)
            .filter(Student.user_id == current_user.id)
            .group_by(Loan.student_id)
            .all()
        )
        loan_counts = dict(loan_counts_query)

        # Nombre total d'emprunts en secours si aucun retour marqué
        total_loans_query = (
            db.session.query(Loan.student_id, func.count(Loan.id))
            .join(Student, Loan.student_id == Student.id)
            .filter(Student.user_id == current_user.id)
            .group_by(Loan.student_id)
            .all()
        )
        total_loans = dict(total_loans_query)

        for s in raw_students:
            cnt = loan_counts.get(s.id, total_loans.get(s.id, 0))
            s.read_count = cnt
            students_list.append(s)

        if student_id:
            student = next((s for s in students_list if s.id == student_id), None)
            if student:
                read_count = student.read_count

    return render_template(
        "ressources/diplome.html",
        student=student,
        read_count=read_count,
        students_list=students_list,
    )


@ressource.route("/ressources/diplome")
def diplome():
    """Redirection 301 permanente vers l'URL canonique optimisée."""
    args = request.args.to_dict()
    return redirect(
        url_for("ressource.diplome_de_lecture_a_imprimer", **args), code=301
    )


@ressource.route("/ressources/marque-pages-a-imprimer")
def marque_pages_a_imprimer():
    """Générateur de marque-pages Emprunt & Avis (4 par page A4)."""
    return render_template("ressources/marque_pages.html")


@ressource.route("/ressources/marque-pages")
def marque_pages():
    """Redirection 301 permanente vers l'URL canonique optimisée."""
    args = request.args.to_dict()
    return redirect(url_for("ressource.marque_pages_a_imprimer", **args), code=301)


@ressource.route("/ressources/charte-coin-lecture-a-imprimer")
def charte_coin_lecture_a_imprimer():
    """Générateur de la Charte du Coin Lecture (A4 / A3)."""
    return render_template("ressources/charte.html")


@ressource.route("/ressources/charte")
def charte():
    """Redirection 301 permanente vers l'URL canonique optimisée."""
    args = request.args.to_dict()
    return redirect(
        url_for("ressource.charte_coin_lecture_a_imprimer", **args), code=301
    )


@ressource.route("/ressources/defi-lecture-bingo-a-imprimer")
def defi_lecture_bingo_a_imprimer():
    """Générateur de Bingo / Défi de lecture personnalisé."""
    return render_template("ressources/bingo.html")


@ressource.route("/ressources/bingo")
def bingo():
    """Redirection 301 permanente vers l'URL canonique optimisée."""
    args = request.args.to_dict()
    return redirect(
        url_for("ressource.defi_lecture_bingo_a_imprimer", **args), code=301
    )


@ressource.route("/ressources/etiquettes")
@premium_required
def etiquettes():
    """Générateur de planches d'étiquettes de genres pour bacs et tranches."""
    user_tags = []
    if current_user.is_authenticated:
        user_tags = (
            Tags.query.filter_by(user_id=current_user.id).order_by(Tags.name).all()
        )
    return render_template("ressources/etiquettes.html", user_tags=user_tags)


@ressource.route("/ressources/fiche-de-lecture-a-imprimer")
def fiche_de_lecture_a_imprimer():
    """Générateur de fiches « Coup de cœur » et fanions de recommandation."""
    return render_template("ressources/fiches_avis.html")


@ressource.route("/ressources/fiches-avis")
def fiches_avis():
    """Redirection 301 permanente vers l'URL canonique optimisée."""
    args = request.args.to_dict()
    return redirect(url_for("ressource.fiche_de_lecture_a_imprimer", **args), code=301)


@ressource.route("/ressources/codes-barres")
@premium_required
def codes_barres():
    """Générateur de planches de codes-barres (livres ou cartes élèves)."""
    books_list = []
    students_list = []
    if current_user.is_authenticated:
        books_list = (
            Book.query.filter_by(user_id=current_user.id).order_by(Book.title).all()
        )
        students_list = (
            Student.query.filter_by(user_id=current_user.id)
            .order_by(Student.name, Student.firstname)
            .all()
        )
    return render_template(
        "ressources/codes_barres.html",
        books_list=books_list,
        students_list=students_list,
    )


@ressource.route("/ressources/passeport-de-lecture-a-imprimer")
def passeport_de_lecture_a_imprimer():
    """Générateur de Passeport de Lecture pliable en livret A5."""
    return render_template("ressources/passeport.html")


@ressource.route("/ressources/passeport")
def passeport():
    """Redirection 301 permanente vers l'URL canonique optimisée."""
    args = request.args.to_dict()
    return redirect(
        url_for("ressource.passeport_de_lecture_a_imprimer", **args), code=301
    )


@ressource.route("/ressources/convertisseur-pdf-livret-a5-a-imprimer")
def convertisseur_pdf_livret():
    """Outil d'imposition PDF en livret A5 imprimable (gratuit)."""
    return render_template("ressources/livret_pdf.html")


@ressource.route("/ressources/livret-pdf")
@ressource.route("/ressources/imposition-pdf")
@ressource.route("/ressources/booklet")
def redirect_livret_pdf():
    """Redirections 301 permanentes vers l'URL canonique optimisée."""
    args = request.args.to_dict()
    return redirect(
        url_for("ressource.convertisseur_pdf_livret", **args), code=301
    )


@ressource.route("/ressources/<path:ressource_slug>")
def ressource_article(ressource_slug):
    """Fallback pour d'éventuels guides éditoriaux statiques."""
    import jinja2
    from flask_babel import get_locale

    lang = str(get_locale())
    templates_to_try = [
        f"ressources/{lang}/{ressource_slug}.html",
        f"ressources/fr/{ressource_slug}.html",
        f"ressources/{ressource_slug}.html",
    ]
    for tmpl in templates_to_try:
        try:
            return render_template(tmpl)
        except jinja2.TemplateNotFound:
            continue
    return render_template("error.html", error=_("Ressource non trouvée")), 404
