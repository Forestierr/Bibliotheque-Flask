import json
from datetime import UTC, date, datetime
from io import BytesIO

import pandas as pd
from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_babel import gettext as _
from flask_login import current_user, login_required
from sqlalchemy import desc, func

from . import db
from .config_plans import MAX_FREE_STUDENTS
from .models import AcademicYearArchive, Book, Loan, Student
from .query import (
    get_students,
    get_students_by_archive_id,
)
from .subscription import premium_required

archive = Blueprint("archive", __name__)


def parse_date(date_str: str | None, default: date) -> date:
    if not date_str:
        return default
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return default


def get_default_school_year(ref_date: date | None = None) -> tuple[str, date, date]:
    """
    Calcule le libellé et la période de l'année scolaire courante :
    - De septembre à décembre de l'année N : année N-(N+1)
    - De janvier à juillet de l'année N : année (N-1)-N
    """
    if ref_date is None:
        ref_date = datetime.now(UTC).date()
    if ref_date.month >= 8:
        start_year = ref_date.year
        end_year = ref_date.year + 1
    else:
        start_year = ref_date.year - 1
        end_year = ref_date.year

    year_label = f"{start_year}-{end_year}"
    start_date = date(start_year, 9, 1)
    end_date = date(end_year, 7, 5)
    return year_label, start_date, end_date


def compute_archive_stats(user_id: int, start_date: date, end_date: date) -> dict:
    students = get_students(user_id)
    total_students = len(students)

    loans_query = (
        db.session.query(Loan)
        .join(Book, Loan.book_id == Book.id)
        .filter(
            Book.user_id == user_id,
            Loan.date_loan >= start_date,
            Loan.date_loan <= end_date,
        )
    )
    total_loans = loans_query.count()
    average_loans = (
        round(total_loans / total_students, 1) if total_students > 0 else 0.0
    )

    top_books_raw = (
        db.session.query(
            Book.title,
            Book.author,
            func.count(Loan.id).label("loan_count"),
        )
        .join(Loan, Book.id == Loan.book_id)
        .filter(
            Book.user_id == user_id,
            Loan.date_loan >= start_date,
            Loan.date_loan <= end_date,
        )
        .group_by(Book.id)
        .order_by(desc("loan_count"), Book.title)
        .limit(10)
        .all()
    )
    top_books = [
        {"title": b[0], "author": b[1] or "", "count": b[2]} for b in top_books_raw
    ]
    most_read_book_title = top_books[0]["title"] if top_books else None
    most_read_book_author = top_books[0]["author"] if top_books else None
    most_read_book_count = top_books[0]["count"] if top_books else 0

    top_readers_raw = (
        db.session.query(
            Student.name,
            Student.firstname,
            func.count(Loan.id).label("loan_count"),
        )
        .join(Loan, Student.id == Loan.student_id)
        .filter(
            Student.user_id == user_id,
            Loan.date_loan >= start_date,
            Loan.date_loan <= end_date,
        )
        .group_by(Student.id)
        .order_by(desc("loan_count"), Student.name, Student.firstname)
        .limit(10)
        .all()
    )
    top_readers = [
        {"name": f"{r[1]} {r[0]}".strip(), "count": r[2]} for r in top_readers_raw
    ]
    top_reader_name = top_readers[0]["name"] if top_readers else None
    top_reader_count = top_readers[0]["count"] if top_readers else 0

    return {
        "total_students": total_students,
        "total_loans": total_loans,
        "average_loans": average_loans,
        "top_books": top_books,
        "top_readers": top_readers,
        "most_read_book_title": most_read_book_title,
        "most_read_book_author": most_read_book_author,
        "most_read_book_count": most_read_book_count,
        "top_reader_name": top_reader_name,
        "top_reader_count": top_reader_count,
    }


@archive.route("/archive/wizard", methods=["GET"])
@login_required
def wizard():
    # 1. Vérification des prêts en cours
    active_loans = (
        db.session.query(Loan, Book, Student)
        .join(Book, Loan.book_id == Book.id)
        .join(Student, Loan.student_id == Student.id)
        .filter(Book.user_id == current_user.id, Loan.date_return.is_(None))
        .order_by(Loan.date_loan.asc())
        .all()
    )

    kept_loan_ids = set(session.get("archive_kept_loans", []))
    # Un emprunt est arbitré s'il est conservé ou s'il a été retourné
    unresolved_loans = [
        loan_item
        for loan_item in active_loans
        if loan_item.Loan.id not in kept_loan_ids
    ]

    has_active_loans = len(active_loans) > 0
    has_unresolved_loans = len(unresolved_loans) > 0

    # Déterminer l'étape courante
    step_arg = request.args.get("step", type=int)
    if not step_arg:
        step = 1 if has_unresolved_loans else 2
    else:
        step = step_arg

    # Règle bloquante : impossible d'aller aux étapes 2 ou 3 s'il reste des encours non arbitrés
    if step > 1 and has_unresolved_loans:
        flash(
            _(
                "Des livres sont encore empruntés. Veuillez tous les arbitrer (retournés, perdus ou conservés) avant de continuer."
            ),
            "warning",
        )
        return redirect(url_for("archive.wizard", step=1))

    # Calcul des dates par défaut
    default_year_label, default_start_date, default_end_date = get_default_school_year()
    start_date_str = request.args.get(
        "start_date", default_start_date.strftime("%Y-%m-%d")
    )
    end_date_str = request.args.get("end_date", default_end_date.strftime("%Y-%m-%d"))
    year_label = request.args.get("year_label", default_year_label)

    start_date = parse_date(start_date_str, default_start_date)
    end_date = parse_date(end_date_str, default_end_date)

    stats = compute_archive_stats(current_user.id, start_date, end_date)

    active_students = get_students(current_user.id)
    # Élèves qui ont un emprunt conservé -> doivent impérativement rester actifs
    kept_student_ids = {
        loan_item.Student.id
        for loan_item in active_loans
        if loan_item.Loan.id in kept_loan_ids
    }

    return render_template(
        "archive/wizard.html",
        step=step,
        active_loans=active_loans,
        unresolved_loans=unresolved_loans,
        has_active_loans=has_active_loans,
        has_unresolved_loans=has_unresolved_loans,
        kept_loan_ids=kept_loan_ids,
        kept_student_ids=kept_student_ids,
        year_label=year_label,
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        stats=stats,
        students=active_students,
        max_free_students=MAX_FREE_STUDENTS,
    )


@archive.route("/archive/wizard/check-loans", methods=["POST"])
@login_required
def check_loans():
    loan_id = request.form.get("loan_id", type=int)
    action = request.form.get("action")  # "return", "lost", "keep", "unkeep"

    if not loan_id or not action:
        if request.is_json:
            return jsonify({"error": "Paramètres manquants"}), 400
        flash(_("Action invalide."), "error")
        return redirect(url_for("archive.wizard", step=1))

    loan = (
        db.session.query(Loan)
        .join(Book, Loan.book_id == Book.id)
        .filter(Book.user_id == current_user.id, Loan.id == loan_id)
        .first()
    )

    if not loan:
        if request.is_json:
            return jsonify({"error": "Prêt introuvable"}), 404
        flash(_("Emprunt introuvable."), "error")
        return redirect(url_for("archive.wizard", step=1))

    kept_loans = set(session.get("archive_kept_loans", []))

    if action == "return":
        loan.date_return = datetime.now(UTC).date()
        loan.notes = None
        kept_loans.discard(loan.id)
        db.session.commit()
        session["archive_kept_loans"] = list(kept_loans)
        flash(_("Le livre a été marqué comme retourné."), "success")

    elif action == "lost":
        loan.date_return = datetime.now(UTC).date()
        loan.notes = "perdu"
        kept_loans.discard(loan.id)
        db.session.commit()
        session["archive_kept_loans"] = list(kept_loans)
        flash(_("Le livre a été déclaré perdu et l'emprunt a été clôturé."), "info")

    elif action == "keep":
        kept_loans.add(loan.id)
        session["archive_kept_loans"] = list(kept_loans)
        flash(
            _("L'emprunt a été marqué comme conservé pour la rentrée prochaine."),
            "info",
        )

    elif action == "unkeep":
        kept_loans.discard(loan.id)
        session["archive_kept_loans"] = list(kept_loans)
        flash(_("La conservation de l'emprunt a été annulée."), "info")

    if request.is_json:
        return jsonify({"success": True, "loan_id": loan_id, "action": action})

    return redirect(url_for("archive.wizard", step=1))


@archive.route("/archive/wizard/commit", methods=["POST"])
@login_required
def commit():
    confirmation = request.form.get("confirmation", "").strip()
    if confirmation.upper() != "ARCHIVER":
        flash(
            _(
                "Veuillez saisir exactement le mot ARCHIVER pour confirmer la clôture de l'année scolaire."
            ),
            "error",
        )
        return redirect(url_for("archive.wizard", step=3))

    # Vérification des dates et libellé
    default_year_label, default_start_date, default_end_date = get_default_school_year()
    year_label = request.form.get("year_label", "").strip() or default_year_label
    start_date = parse_date(request.form.get("start_date"), default_start_date)
    end_date = parse_date(request.form.get("end_date"), default_end_date)

    if start_date >= end_date:
        flash(
            _("La date de début doit être antérieure à la date de fin."),
            "error",
        )
        return redirect(url_for("archive.wizard", step=3))

    # Récupérer les élèves cochés pour l'archivage
    archived_student_ids_raw = request.form.getlist("archived_students")
    archived_ids = {int(x) for x in archived_student_ids_raw if x.isdigit()}

    # Vérifier qu'aucun élève à archiver n'a d'emprunt en cours non retourné
    unreturned_loans = (
        db.session.query(Loan, Book, Student)
        .join(Book, Loan.book_id == Book.id)
        .join(Student, Loan.student_id == Student.id)
        .filter(
            Book.user_id == current_user.id,
            Loan.date_return.is_(None),
            Loan.student_id.in_(archived_ids),
        )
        .all()
    )

    if unreturned_loans:
        names = ", ".join(
            {
                f"{item.Student.firstname} {item.Student.name}"
                for item in unreturned_loans
            }
        )
        flash(
            _(
                "Impossible d'archiver les élèves suivants car ils ont encore des livres empruntés : %(names)s. Veuillez régulariser leurs prêts.",
                names=names,
            ),
            "error",
        )
        return redirect(url_for("archive.wizard", step=1))

    # Calcul des statistiques consolidées pour l'archive
    stats = compute_archive_stats(current_user.id, start_date, end_date)

    # Création du snapshot de l'archive
    new_archive = AcademicYearArchive(
        user_id=current_user.id,
        year_label=year_label,
        start_date=start_date,
        end_date=end_date,
        archived_at=datetime.now(UTC),
        total_students=stats["total_students"],
        total_loans=stats["total_loans"],
        average_loans_per_student=stats["average_loans"],
        most_read_book_title=stats["most_read_book_title"],
        most_read_book_author=stats["most_read_book_author"],
        most_read_book_count=stats["most_read_book_count"],
        top_reader_name=stats["top_reader_name"],
        top_reader_count=stats["top_reader_count"],
        top_books_json=json.dumps(stats["top_books"], ensure_ascii=False),
        top_readers_json=json.dumps(stats["top_readers"], ensure_ascii=False),
    )
    db.session.add(new_archive)
    db.session.flush()

    # Archivage des élèves sortants
    now = datetime.now(UTC)
    active_students = get_students(current_user.id)
    for student in active_students:
        if student.id in archived_ids:
            student.is_archived = True
            student.archived_at = now
            student.archived_year_id = new_archive.id

    # Nettoyage de la session
    session.pop("archive_kept_loans", None)

    db.session.commit()

    flash(
        _(
            "L'année scolaire %(year)s a été clôturée avec succès ! Vos élèves sortants ont été archivés et votre quota a été réinitialisé.",
            year=new_archive.year_label,
        ),
        "success",
    )
    return redirect(url_for("archive.detail", archive_id=new_archive.id))


@archive.route("/archive/<int:archive_id>", methods=["GET"])
@login_required
def detail(archive_id: int):
    archive_item = AcademicYearArchive.query.filter_by(
        id=archive_id, user_id=current_user.id
    ).first_or_404()

    archived_students = get_students_by_archive_id(current_user.id, archive_item.id)

    # Calcul du nombre d'emprunts de chaque élève sur la période de l'archive
    student_loan_counts = {}
    if archived_students:
        counts = (
            db.session.query(Loan.student_id, func.count(Loan.id))
            .join(Book, Loan.book_id == Book.id)
            .filter(
                Book.user_id == current_user.id,
                Loan.student_id.in_([s.id for s in archived_students]),
                Loan.date_loan >= archive_item.start_date,
                Loan.date_loan <= archive_item.end_date,
            )
            .group_by(Loan.student_id)
            .all()
        )
        student_loan_counts = dict(counts)

    return render_template(
        "archive/detail.html",
        archive=archive_item,
        students=archived_students,
        student_loan_counts=student_loan_counts,
    )


@archive.route("/archive/<int:archive_id>/print", methods=["GET"])
@login_required
@premium_required
def print_summary(archive_id: int):
    archive_item = AcademicYearArchive.query.filter_by(
        id=archive_id, user_id=current_user.id
    ).first_or_404()

    archived_students = get_students_by_archive_id(current_user.id, archive_item.id)

    student_loan_counts = {}
    if archived_students:
        counts = (
            db.session.query(Loan.student_id, func.count(Loan.id))
            .join(Book, Loan.book_id == Book.id)
            .filter(
                Book.user_id == current_user.id,
                Loan.student_id.in_([s.id for s in archived_students]),
                Loan.date_loan >= archive_item.start_date,
                Loan.date_loan <= archive_item.end_date,
            )
            .group_by(Loan.student_id)
            .all()
        )
        student_loan_counts = dict(counts)

    return render_template(
        "archive/print_summary.html",
        archive=archive_item,
        students=archived_students,
        student_loan_counts=student_loan_counts,
    )


@archive.route("/archive/<int:archive_id>/export-excel", methods=["GET"])
@login_required
@premium_required
def export_excel(archive_id: int):
    archive_item = AcademicYearArchive.query.filter_by(
        id=archive_id, user_id=current_user.id
    ).first_or_404()

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Feuille 1 : Synthèse
        summary_data = [
            {"Indicateur": "Année scolaire", "Valeur": archive_item.year_label},
            {
                "Indicateur": "Date de début",
                "Valeur": archive_item.start_date.strftime("%d/%m/%Y"),
            },
            {
                "Indicateur": "Date de fin",
                "Valeur": archive_item.end_date.strftime("%d/%m/%Y"),
            },
            {
                "Indicateur": "Date de clôture",
                "Valeur": archive_item.archived_at.strftime("%d/%m/%Y %H:%M"),
            },
            {
                "Indicateur": "Effectif total de la promotion",
                "Valeur": archive_item.total_students,
            },
            {
                "Indicateur": "Volume total d'emprunts",
                "Valeur": archive_item.total_loans,
            },
            {
                "Indicateur": "Moyenne d'emprunts par élève",
                "Valeur": archive_item.average_loans_per_student,
            },
            {
                "Indicateur": "Livre le plus lu",
                "Valeur": f"{archive_item.most_read_book_title or ''} ({archive_item.most_read_book_count} prêts)",
            },
            {
                "Indicateur": "Plus grand lecteur",
                "Valeur": f"{archive_item.top_reader_name or ''} ({archive_item.top_reader_count} prêts)",
            },
        ]
        pd.DataFrame(summary_data).to_excel(writer, index=False, sheet_name="Synthèse")

        # Feuille 2 : Top Livres
        top_books = archive_item.top_books
        if top_books:
            books_data = [
                {
                    "Rang": i + 1,
                    "Titre": b.get("title", ""),
                    "Auteur": b.get("author", ""),
                    "Nombre d'emprunts": b.get("count", 0),
                }
                for i, b in enumerate(top_books)
            ]
            pd.DataFrame(books_data).to_excel(
                writer, index=False, sheet_name="Top Livres"
            )

        # Feuille 3 : Palmarès Élèves
        top_readers = archive_item.top_readers
        if top_readers:
            readers_data = [
                {
                    "Rang": i + 1,
                    "Élève": r.get("name", ""),
                    "Livres empruntés": r.get("count", 0),
                }
                for i, r in enumerate(top_readers)
            ]
            pd.DataFrame(readers_data).to_excel(
                writer, index=False, sheet_name="Palmarès Élèves"
            )

        # Feuille 4 : Promotion des élèves
        archived_students = get_students_by_archive_id(current_user.id, archive_item.id)
        counts = {}
        if archived_students:
            counts = dict(
                db.session.query(Loan.student_id, func.count(Loan.id))
                .join(Book, Loan.book_id == Book.id)
                .filter(
                    Book.user_id == current_user.id,
                    Loan.student_id.in_([s.id for s in archived_students]),
                    Loan.date_loan >= archive_item.start_date,
                    Loan.date_loan <= archive_item.end_date,
                )
                .group_by(Loan.student_id)
                .all()
            )
            students_data = [
                {
                    "Nom": s.name,
                    "Prénom": s.firstname,
                    "Emprunts dans l'année": counts.get(s.id, 0),
                    "Date d'archivage": s.archived_at.strftime("%d/%m/%Y")
                    if s.archived_at
                    else "",
                }
                for s in archived_students
            ]
            pd.DataFrame(students_data).to_excel(
                writer, index=False, sheet_name="Élèves"
            )

    output.seek(0)
    filename = f"bilan_lecture_{archive_item.year_label}.xlsx"
    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@archive.route("/archive/<int:archive_id>/delete", methods=["POST"])
@login_required
def delete(archive_id: int):
    archive_item = AcademicYearArchive.query.filter_by(
        id=archive_id, user_id=current_user.id
    ).first_or_404()

    year_label = archive_item.year_label

    # Réactivation des élèves associés à cette promotion
    students = Student.query.filter_by(
        user_id=current_user.id, archived_year_id=archive_item.id
    ).all()
    for student in students:
        student.is_archived = False
        student.archived_at = None
        student.archived_year_id = None

    db.session.delete(archive_item)
    db.session.commit()

    flash(
        _(
            "L'archive de l'année scolaire %(year)s a été supprimée et les élèves ont été réactivés dans votre classe.",
            year=year_label,
        ),
        "info",
    )
    return redirect(url_for("auth.reglage") + "?tab=archive")
