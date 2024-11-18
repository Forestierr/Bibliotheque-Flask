# eleve.py

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from sqlalchemy import and_, or_

from .models import Student, Loan, Book
from . import db

eleve = Blueprint('eleve', __name__)

@eleve.route('/eleve')
@login_required
def eleve_db():
    # students = Student.query.filter_by(user_id=current_user.id).all()
    # students = [(student.name, student.firstname) for student in students]

    # Query all students from the current user and add the books if the student has loans
    students_with_loans = db.session.query(Student, Loan, Book).filter(Student.user_id == current_user.id).outerjoin(Loan, and_(Student.id == Loan.student_id, Loan.date_return == None)).outerjoin(Book, Loan.book_id == Book.id).all()
    students = [(student, book) for (student, _, book) in students_with_loans]


    return render_template('eleve.html', students=students)

@eleve.route('/eleve/ajout', methods=['GET', 'POST'])
@login_required
def ajouter_eleve():
    if request.method == 'POST':
        name = request.form.get('name')
        firstname = request.form.get('firstname')

        # verify if the fields are not empty
        if not name or not firstname:
            flash('Veuillez remplir tous les champs.')
            return redirect(url_for('eleve.ajouter_eleve'))

        # verify if the student already exists
        student = Student.query.filter_by(user_id=current_user.id, name=name, firstname=firstname).first()
        if student:
            flash('L\'élève existe déjà.')
            return redirect(url_for('eleve.ajouter_eleve'))

        new_student = Student(user_id=current_user.id, name=name, firstname=firstname)
        db.session.add(new_student)
        db.session.commit()

        redirect(url_for('eleve.eleve_db'))

    return render_template('eleve_add.html')

@eleve.route('/eleve/<firstname> <name>')
@login_required
def eleve_infos(firstname, name):
    student_with_loans = db.session.query(Student, Loan, Book).filter(Student.user_id == current_user.id, Student.name == name, Student.firstname == firstname).outerjoin(Loan, Student.id == Loan.student_id).filter(Loan.date_return == None).outerjoin(Book, Loan.book_id == Book.id).all()

    old_loans = db.session.query(Student, Loan, Book).filter(Student.user_id == current_user.id, Student.name == name, Student.firstname == firstname).outerjoin(Loan, Student.id == Loan.student_id).filter(Loan.date_return != None).outerjoin(Book, Loan.book_id == Book.id).all()

    if student_with_loans:
        student = student_with_loans[0][0]
        books = [(loan, book) for (_, loan, book) in student_with_loans]
    else:
        student = Student.query.filter_by(user_id=current_user.id, name=name, firstname=firstname).first()
        books = []

    if old_loans:
        old_books = [(loan, book) for (_, loan, book) in old_loans]
    else:
        old_books = []

    # change the date format from 2024-12-31 to 31 dec. 2024
    for i, (loan, _) in enumerate(books):
        loan.date_loan = loan.date_loan.strftime('%d %b %Y')
        if loan.date_return:
            loan.date_return = loan.date_return.strftime('%d %b %Y')

    for i, (loan, _) in enumerate(old_books):
        loan.date_loan = loan.date_loan.strftime('%d %b %Y')
        if loan.date_return:
            loan.date_return = loan.date_return.strftime('%d %b %Y')

    return render_template('eleve.html', student=student, books=books, old_books=old_books)

@eleve.route('/eleve/<name> <firstname>/delete')
@login_required
def eleve_delete(name, firstname):
    student = Student.query.filter_by(user_id=current_user.id, name=name, firstname=firstname).first()

    loans = Loan.query.filter_by(student_id=student.id).all()
    for loan in loans:
        db.session.delete(loan)

    db.session.delete(student)
    db.session.commit()

    return redirect(url_for('eleve.eleve_db'))