# emprunt.py

from flask import Blueprint, render_template, redirect, url_for, request, flash, make_response, jsonify
from flask_login import login_required, current_user
from sqlalchemy import and_

from .models import Book, Loan, Student
from . import db

emprunt = Blueprint('emprunt', __name__)

@emprunt.route('/emprunt', methods=['GET', 'POST'])
@login_required
def emprunt_db():
    loans = []
    only_active_loans = True

    if request.method == 'POST':
        active_loan = request.form.get('active_loan')

        if active_loan:
            only_active_loans = False
            loans = db.session.query(Book, Loan, Student).filter(Book.user_id == current_user.id, Loan.date_return == None).outerjoin(Loan, Book.id == Loan.book_id).outerjoin(Student, Loan.student_id == Student.id).all()
        else:
            only_active_loans = True
            loans = db.session.query(Book, Loan, Student).filter(Book.user_id == current_user.id).outerjoin(Loan, Book.id == Loan.book_id).outerjoin(Student, Loan.student_id == Student.id).all()
    else:
        loans = db.session.query(Book, Loan, Student).filter(Book.user_id == current_user.id).outerjoin(Loan, Book.id == Loan.book_id).outerjoin(Student, Loan.student_id == Student.id).all()

    return render_template('emprunt.html', loans=loans, only_active_loans=only_active_loans)

@emprunt.route('/emprunt/<id>/delete', methods=['GET', 'POST'])
@login_required
def delete_loan(id):
    loan = db.session.query(Loan).filter(Loan.id == id).first()

    book = db.session.query(Book).filter(Book.id == loan.book_id).first()

    if book.user_id != current_user.id:
        return redirect(url_for('emprunt.emprunt_db'))

    if loan:
        db.session.delete(loan)
        db.session.commit()

    return redirect(url_for('emprunt.emprunt_db'))