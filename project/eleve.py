# main.py

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from .models import Student, Loan, Book
from . import db

eleve = Blueprint('eleve', __name__)

@eleve.route('/eleve')
@login_required
def eleve_db():
    # students = Student.query.filter_by(user_id=current_user.id).all()
    # students = [(student.name, student.firstname) for student in students]

    # Query all students from the current user and add the books if the student has loans
    students_with_loans = db.session.query(Student, Loan, Book).filter(Student.user_id == current_user.id).outerjoin(Loan, Student.id == Loan.student_id).outerjoin(Book, Loan.book_id == Book.id).all()
    students = [(student, book) for (student, _, book) in students_with_loans]

    print(students)

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
    #student = Student.query.filter_by(user_id=current_user.id, name=name, firstname=firstname).first()
    #student = (student.name, student.firstname)

    student_with_loans = db.session.query(Student, Loan, Book).filter(Student.user_id == current_user.id, Student.name == name, Student.firstname == firstname).outerjoin(Loan, Student.id == Loan.student_id).outerjoin(Book, Loan.book_id == Book.id).all()
    student = [(student, book) for (student, _, book) in student_with_loans]

    return render_template('eleve.html', student=student[0])

@eleve.route('/eleve/<name> <firstname>/delete')
@login_required
def eleve_delete(name, firstname):
    student = Student.query.filter_by(user_id=current_user.id, name=name, firstname=firstname).first()
    db.session.delete(student)
    db.session.commit()

    return redirect(url_for('eleve.eleve_db'))