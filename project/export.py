from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
from flask import Blueprint, send_file
from flask_login import current_user, login_required

from . import db
from .models import Book, Loan, Student

export = Blueprint("export", __name__)


@export.route("/export/books")
@login_required
def export_books():
    books = Book.query.filter_by(user_id=current_user.id).all()

    data = []
    for book in books:
        data.append(
            {
                "Titre": book.title,
                "Auteur": book.author,
                "Éditeur": book.editor,
                "ISBN": book.isbn,
                "Année": book.year,
                "Type": book.type,
            }
        )

    df = pd.DataFrame(data)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Livres")
    output.seek(0)

    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    return send_file(
        output, download_name=f"livres_{date_str}.xlsx", as_attachment=True
    )


@export.route("/export/students_reads")
@login_required
def export_students_reads():
    # Élèves et les livres qu'ils ont lu (date de retour remplie, ou non)
    # On va faire une ligne par livre lu/emprunté par élève
    loans = (
        db.session.query(Loan, Book, Student)
        .join(Book, Loan.book_id == Book.id)
        .join(Student, Loan.student_id == Student.id)
        .filter(Book.user_id == current_user.id)
        .order_by(Student.name, Student.firstname, Loan.date_loan.desc())
        .all()
    )

    data = []
    for loan, book, student in loans:
        data.append(
            {
                "Nom Élève": student.name,
                "Prénom Élève": student.firstname,
                "Titre du Livre": book.title,
                "Auteur": book.author,
                "Date Emprunt": loan.date_loan.strftime("%Y-%m-%d")
                if loan.date_loan
                else "",
                "Date Retour": loan.date_return.strftime("%Y-%m-%d")
                if loan.date_return
                else "En cours",
            }
        )

    df = pd.DataFrame(data)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Lectures des élèves")
    output.seek(0)

    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    return send_file(
        output, download_name=f"lectures_eleves_{date_str}.xlsx", as_attachment=True
    )


@export.route("/export/active_loans")
@login_required
def export_active_loans():
    loans = (
        db.session.query(Loan, Book, Student)
        .join(Book, Loan.book_id == Book.id)
        .join(Student, Loan.student_id == Student.id)
        .filter(Book.user_id == current_user.id, Loan.date_return.is_(None))
        .order_by(Loan.date_loan.desc())
        .all()
    )

    data = []
    for loan, book, student in loans:
        data.append(
            {
                "Titre du Livre": book.title,
                "Auteur": book.author,
                "Nom Élève": student.name,
                "Prénom Élève": student.firstname,
                "Date Emprunt": loan.date_loan.strftime("%Y-%m-%d")
                if loan.date_loan
                else "",
            }
        )

    df = pd.DataFrame(data)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Prêts en cours")
    output.seek(0)

    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    return send_file(
        output, download_name=f"prets_en_cours_{date_str}.xlsx", as_attachment=True
    )


@export.route("/export/all_loans")
@login_required
def export_all_loans():
    loans = (
        db.session.query(Loan, Book, Student)
        .join(Book, Loan.book_id == Book.id)
        .join(Student, Loan.student_id == Student.id)
        .filter(Book.user_id == current_user.id)
        .order_by(Loan.date_loan.desc())
        .all()
    )

    data = []
    for loan, book, student in loans:
        data.append(
            {
                "Titre du Livre": book.title,
                "Auteur": book.author,
                "Nom Élève": student.name,
                "Prénom Élève": student.firstname,
                "Date Emprunt": loan.date_loan.strftime("%Y-%m-%d")
                if loan.date_loan
                else "",
                "Date Retour": loan.date_return.strftime("%Y-%m-%d")
                if loan.date_return
                else "En cours",
                "Statut": "En cours" if loan.date_return is None else "Terminé",
            }
        )

    df = pd.DataFrame(data)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Tous les prêts")
    output.seek(0)

    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    return send_file(
        output, download_name=f"historique_prets_{date_str}.xlsx", as_attachment=True
    )
