# emprunt.py
from datetime import date

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

        if active_loan == '0':
            only_active_loans = False
            loans = db.session.query(Book, Loan, Student).filter(Book.user_id == current_user.id, Loan.date_loan is not None, Loan.date_return == None).join(Loan, Book.id == Loan.book_id).join(Student, Loan.student_id == Student.id).all()
        else:
            only_active_loans = True
            loans = db.session.query(Book, Loan, Student).filter(Book.user_id == current_user.id, Loan.date_loan is not None).join(Loan, Book.id == Loan.book_id).join(Student, Loan.student_id == Student.id).all()

    if not loans:
        if request.method == 'POST' and active_loan == '0':
            flash('Aucun livre n\'est actuellement en prêt.', 'info')
        loans = db.session.query(Book, Loan, Student).filter(Book.user_id == current_user.id, Loan.date_loan is not None).join(Loan, Book.id == Loan.book_id).join(Student, Loan.student_id == Student.id).all()

    # change the date format from 2024-12-31 to 31 dec. 2024
    for i, loan in enumerate(loans):
        loan[1].date_loan = loan[1].date_loan.strftime('%d %b %Y')
        if loan[1].date_return:
            loan[1].date_return = loan[1].date_return.strftime('%d %b %Y')

    return render_template('emprunt/emprunt.html', loans=loans, only_active_loans=only_active_loans)


@emprunt.route('/emprunt/<id>', methods=['GET', 'POST'])
@login_required
def return_loan(id):
    from_url = request.referrer

    loan = db.session.query(Loan).filter(Loan.id == id).first()

    if loan:
        loan.date_return = date.today()
        db.session.commit()


    return redirect(from_url)


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


@emprunt.route('/emprunt/delete_all', methods=['POST'])
@login_required
def delete_all_loans():
    loans = db.session.query(Loan).join(Book, Loan.book_id == Book.id).filter(Book.user_id == current_user.id).all()

    for loan in loans:
        db.session.delete(loan)

    db.session.commit()

    return redirect(url_for('auth.reglage'))
