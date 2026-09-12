# eleve.py

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import gettext as _
from flask_login import current_user, login_required
from sqlalchemy import and_, or_

from . import db
from .config_plans import MAX_FREE_STUDENTS
from .models import Loan, Student
from .query import (
    get_all_students_info,
    get_search_all_students_info,
    get_student_infos,
)

eleve = Blueprint("eleve", __name__)


@eleve.route("/eleve")
@login_required
def eleve_db():
    students = get_all_students_info(current_user.id)

    return render_template("eleve/eleve.html", students=students)


@eleve.route("/eleve/ajout", methods=["GET", "POST"])
@login_required
def ajouter_eleve():
    if request.method == "POST":
        # Vérification du quota pour les utilisateurs en plan gratuit
        if not current_user.is_premium:
            current_count = Student.query.filter_by(user_id=current_user.id).count()
            if current_count >= MAX_FREE_STUDENTS:
                msg = _(
                    "Vous avez atteint la limite de %(max)s élèves du plan gratuit. Vos élèves existants restent utilisables. Pour en ajouter d'autres, passez Premium ou supprimez un élève existant.",
                    max=MAX_FREE_STUDENTS,
                )
                if (
                    request.headers.get("X-Requested-With") == "XMLHttpRequest"
                    or request.is_json
                ):
                    return jsonify({"error": "quota_reached", "message": msg}), 403
                flash(msg, "warning")
                return redirect(url_for("subscription.tarifs"))

        name = request.form.get("name")
        firstname = request.form.get("firstname")

        # verify if the fields are not empty
        if not name or not firstname:
            flash(_("Veuillez remplir tous les champs."))
            return redirect(url_for("eleve.ajouter_eleve"))

        # verify if the student already exists
        student = Student.query.filter_by(
            user_id=current_user.id, name=name, firstname=firstname
        ).first()
        if student:
            flash(_("L'élève existe déjà."))
            return redirect(url_for("eleve.ajouter_eleve"))

        new_student = Student(user_id=current_user.id, name=name, firstname=firstname)
        db.session.add(new_student)
        db.session.commit()

        return redirect(url_for("eleve.eleve_db"))

    student_count = Student.query.filter_by(user_id=current_user.id).count()
    quota_reached = not current_user.is_premium and student_count >= MAX_FREE_STUDENTS
    return render_template(
        "eleve/eleve_add.html",
        quota_reached=quota_reached,
        max_students=MAX_FREE_STUDENTS,
        student_count=student_count,
    )


@eleve.route("/eleve/<id>")
@login_required
def eleve_infos(id):
    student, books, old_books = get_student_infos(current_user.id, id)

    return render_template(
        "eleve/eleve_info.html", student=student, books=books, old_books=old_books
    )


@eleve.route("/eleve/<id>/delete", methods=["POST"])
@login_required
def eleve_delete(id):
    student = Student.query.filter_by(user_id=current_user.id, id=id).first()

    loans = Loan.query.filter_by(student_id=student.id).all()
    for loan in loans:
        db.session.delete(loan)

    db.session.delete(student)
    db.session.commit()

    return redirect(url_for("eleve.eleve_db"))


@eleve.route("/eleve/delete_all", methods=["POST"])
@login_required
def eleve_delete_all():
    students = Student.query.filter_by(user_id=current_user.id).all()
    for student in students:
        loans = Loan.query.filter_by(student_id=student.id).all()
        for loan in loans:
            db.session.delete(loan)
        db.session.delete(student)
    db.session.commit()

    return redirect(url_for("auth.reglage"))


@eleve.route("/eleve/search-preview", methods=["POST"])
@login_required
def search_preview():
    search = request.form.get("search")
    students = (
        Student.query.filter(
            and_(
                Student.user_id == current_user.id,
                or_(
                    Student.name.like("%" + search + "%"),
                    Student.firstname.like("%" + search + "%"),
                ),
            )
        )
        .limit(5)
        .all()
    )

    return render_template("eleve/search_preview.html", students=students)


@eleve.route("/eleve/search", methods=["POST"])
@login_required
def search():
    search = request.form.get("search")

    students = get_search_all_students_info(current_user.id, search)

    return render_template("eleve/eleve_list.html", students=students)
