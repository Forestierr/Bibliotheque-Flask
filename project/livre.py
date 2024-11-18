# livre.py
import math
from math import floor

from flask import Blueprint, render_template, redirect, url_for, request, flash, make_response, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_, and_, text, DateTime
from datetime import datetime, date

from .models import Book, Student, Loan
from . import db

livre = Blueprint('livre', __name__)

@livre.route('/livre', methods=['GET', 'POST'])
@livre.route('/livre/<int:page>/', methods=['GET', 'POST'])
@login_required
def livre_db(page=1):
    n_books_by_page = 10
    # get the number of books
    nb_books = db.session.query(Book).filter(Book.user_id == current_user.id).count()
    # nombre de page
    nb_page = math.ceil(nb_books / n_books_by_page)

    books = []

    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        editor = request.form.get('editor')
        year = request.form.get('year')
        type = request.form.get('type')
        isbn = request.form.get('isbn')
        student = request.form.get('student')

        if title or author or editor or year or type or isbn or student:
            books = db.session.query(Book, Loan, Student).filter(Book.user_id == current_user.id, or_(
                    Book.title.ilike('%' + title + '%') if title else text(''),
                    Book.author.ilike('%' + author + '%') if author else text(''),
                    Book.editor.ilike('%' + editor + '%') if editor else text(''),
                    Book.year.ilike('%' + year + '%') if year else text(''),
                    Book.type.ilike('%' + type + '%') if type else text(''),
                    Book.isbn.ilike('%' + isbn + '%') if isbn else text(''),
                    Student.name.ilike('%' + student + '%') if student else text(''),
                    Student.firstname.ilike('%' + student + '%') if student else text('')
                )).outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return == None)).outerjoin(Student, Loan.student_id == Student.id).all()

            nb_books = len(books)
            nb_page = math.ceil(nb_books / n_books_by_page)

            books = books[:n_books_by_page]

    if not books:
        # Query books and add the student name if the book is loaned
        books = (
            db.session.query(Book, Loan, Student)
            .filter(Book.user_id == current_user.id)
            .outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return == None))
            .outerjoin(Student, Loan.student_id == Student.id )
            .limit(n_books_by_page).offset((int(page) - 1) * n_books_by_page)
        )

    books = [(book, student) for (book, _, student) in books]

    return render_template('livre.html', books=books, nb_page=nb_page, page=int(page))


@livre.route('/livre/ajout', methods=['GET', 'POST'])
@login_required
def livre_ajout():
    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        editor = request.form.get('editor')
        year = request.form.get('year')
        type = request.form.get('type')
        isbn = request.form.get('isbn')

        # to avoid empty string (because isbn is a required field)
        if (isbn == ''):
            isbn = None

        if (author == "None"):
            author = ""

        if (editor == "undefined"):
            editor = ""

        if not title:
            flash('Veuillez ajouter un titre.')
            return redirect(url_for('livre.livre_ajout'))

        # Check if the book already exists
        book = Book.query.filter_by(user_id=current_user.id, title=title).first()
        if book:
            flash('Ce livre existe déjà.')
            return redirect(url_for('livre.livre_ajout'))

        new_book = Book(title=title, author=author, editor=editor, year=year, type=type, isbn=isbn, user_id=current_user.id)
        db.session.add(new_book)
        db.session.commit()

        return redirect(url_for('livre.livre_db'))

    return render_template('livre_ajout.html')


@livre.route('/livre/scann', methods=['GET', 'POST'])
@login_required
def livre_scann():

    return render_template('livre_scann_live.html')


@livre.route('/livre/<id>/edit', methods=['GET', 'POST'])
@login_required
def livre_edit(id):
    book = Book.query.filter_by(id=id, user_id=current_user.id).first()

    if not book:
        return redirect(url_for('livre.livre_db'))

    # Get all students from the current user
    students = Student.query.filter_by(user_id=current_user.id).all()
    students = [(student.id, student.name, student.firstname) for student in students]

    loan = Loan.query.filter_by(book_id=id, date_return=None).first()
    student = Student.query.filter_by(id=loan.student_id).first() if loan else None

    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        editor = request.form.get('editor')
        year = request.form.get('year')
        type = request.form.get('type')
        isbn = request.form.get('isbn')
        student = request.form.get('student')

        if not title:
            flash('Veuillez remplir le titre.')
            return redirect(url_for('livre.livre_edit', id=id))

        # Update the book
        book.title = title
        book.author = author
        book.editor = editor
        book.year = year
        book.type = type
        book.isbn = isbn

        # take the student in the database
        student = Student.query.filter_by(id=student, user_id=current_user.id).first()

        if student:
            if loan:
                if loan.student_id != student.id:
                    # changement de l'élève
                    # fin de la location
                    loan.date_return = date.today()

                    # nouvelle location
                    new_loan = Loan(student_id=student.id, book_id=id, date_loan=date.today())
                    db.session.add(new_loan)
            else:
                # nouvelle location
                new_loan = Loan(student_id=student.id, book_id=id, date_loan=date.today())
                db.session.add(new_loan)
        else:
            if loan:
                # fin de la location
                loan.date_return = date.today()

        db.session.commit()

        return redirect(url_for('livre.livre_db'))

    return render_template('livre_edit.html', book=book, students=students, student=student)

@livre.route('/livre/<id>/delete')
@login_required
def livre_delete(id):
    book = Book.query.filter_by(id=id, user_id=current_user.id).first()

    loan = Loan.query.filter_by(book_id=id).all()
    for l in loan:
        db.session.delete(l)

    db.session.delete(book)
    db.session.commit()

    return redirect(url_for('livre.livre_db'))

@livre.route('/livre/<isbn>/exist')
@login_required
def livre_exist(isbn):
    print(isbn)
    book = Book.query.filter_by(isbn=isbn, user_id=current_user.id).first()
    print(book)
    if book:
        data = {'id': book.id}
        response = make_response(jsonify(data), 200)

        return {'id': book.id}

    return make_response('No Content', 204)