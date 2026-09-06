# ressource.py

from flask import Blueprint, render_template, request
from flask_babel import gettext as _
from flask_login import current_user

from .models import Book, Loan, Student, Tags

ressource = Blueprint("ressource", __name__)


@ressource.route("/ressources")
def index():
    """Catalogue principal des ressources pédagogiques et outils imprimables."""
    return render_template("ressources/index.html")


@ressource.route("/ressources/diplome")
def diplome():
    """Générateur de diplôme de lecture personnalisé."""
    student_id = request.args.get("student_id", type=int)
    student = None
    read_count = 0
    students_list = []

    if current_user.is_authenticated:
        students_list = (
            Student.query.filter_by(user_id=current_user.id)
            .order_by(Student.name, Student.firstname)
            .all()
        )
        if student_id:
            student = Student.query.filter_by(
                id=student_id, user_id=current_user.id
            ).first()
            if student:
                # Nombre de livres dont la date de retour est renseignée
                read_count = (
                    Loan.query.filter_by(student_id=student.id)
                    .filter(Loan.date_return.isnot(None))
                    .count()
                )

    return render_template(
        "ressources/diplome.html",
        student=student,
        read_count=read_count,
        students_list=students_list,
    )


@ressource.route("/ressources/marque-pages")
def marque_pages():
    """Générateur de marque-pages Emprunt & Avis (4 par page A4)."""
    return render_template("ressources/marque_pages.html")


@ressource.route("/ressources/charte")
def charte():
    """Générateur de la Charte du Coin Lecture (A4 / A3)."""
    return render_template("ressources/charte.html")


@ressource.route("/ressources/bingo")
def bingo():
    """Générateur de Bingo / Défi de lecture personnalisé."""
    return render_template("ressources/bingo.html")


@ressource.route("/ressources/etiquettes")
def etiquettes():
    """Générateur de planches d'étiquettes de genres pour bacs et tranches."""
    user_tags = []
    if current_user.is_authenticated:
        user_tags = (
            Tags.query.filter_by(user_id=current_user.id).order_by(Tags.name).all()
        )
    return render_template("ressources/etiquettes.html", user_tags=user_tags)


@ressource.route("/ressources/fiches-avis")
def fiches_avis():
    """Générateur de fiches « Coup de cœur » et fanions de recommandation."""
    return render_template("ressources/fiches_avis.html")


@ressource.route("/ressources/codes-barres")
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


@ressource.route("/ressources/passeport")
def passeport():
    """Générateur de Passeport de Lecture pliable en livret A5."""
    return render_template("ressources/passeport.html")


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
