# eleve.py

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from sqlalchemy import and_, or_

from .models import Student, Loan, Book
from . import db
from .query import *

eleve = Blueprint('eleve', __name__)

@eleve.route('/eleve')
@login_required
def eleve_db():
    students = get_all_students_info(current_user.id)

    return render_template('eleve/eleve.html', students=students)

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

    return render_template('eleve/eleve_add.html')

@eleve.route('/eleve/<id>')
@login_required
def eleve_infos(id):
    student, books, old_books = get_student_infos(current_user.id, id)

    return render_template('eleve/eleve_info.html', student=student, books=books, old_books=old_books)


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

@eleve.route('/eleve/delete_all', methods=['POST'])
@login_required
def eleve_delete_all():
    students = Student.query.filter_by(user_id=current_user.id).all()
    for student in students:
        loans = Loan.query.filter_by(student_id=student.id).all()
        for loan in loans:
            db.session.delete(loan)
        db.session.delete(student)
    db.session.commit()

    return redirect(url_for('auth.reglage'))
