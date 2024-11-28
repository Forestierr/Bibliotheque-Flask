# livre.py
import math
from math import floor
import json

from flask import Blueprint, render_template, redirect, url_for, request, flash, make_response, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_, and_, text, DateTime
from datetime import datetime, date

from .models import Book, Student, Loan, Tags, BookTags
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
        tags = request.form.get('tags')

        # TODO : add tags in the search
        if title or author or editor or year or type or isbn or student or tags:
            tags = tags.split(',')
            books = db.session.query(Book, Loan, Student).filter(Book.user_id == current_user.id, or_(
                    Book.title.ilike('%' + title + '%') if title else text(''),
                    Book.author.ilike('%' + author + '%') if author else text(''),
                    Book.editor.ilike('%' + editor + '%') if editor else text(''),
                    Book.year.ilike('%' + year + '%') if year else text(''),
                    Book.type.ilike('%' + type + '%') if type else text(''),
                    Book.isbn.ilike('%' + isbn + '%') if isbn else text(''),
                    Student.name.ilike('%' + student + '%') if student else text(''),
                    Student.firstname.ilike('%' + student + '%') if student else text(''),
                    and_(Tags.name.in_(tags), Book.id == BookTags.book_id,Tags.id == BookTags.tag_id)
                )).outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return == None)).outerjoin(Student, Loan.student_id == Student.id).all()

            nb_books = len(books)
            nb_page = math.ceil(nb_books / n_books_by_page)

            books = books[:n_books_by_page]

    if not books:
        if request.method == 'POST':
            flash('Aucun livre n\'a été trouvé lors de la recherche.', 'info')

        # Query books and add the student name if the book is loaned
        books = (
            db.session.query(Book, Loan, Student)
            .filter(Book.user_id == current_user.id)
            .outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return == None))
            .outerjoin(Student, Loan.student_id == Student.id )
            .limit(n_books_by_page).offset((int(page) - 1) * n_books_by_page)
        )

    books = [(book, student) for (book, _, student) in books]
    all_students = Student.query.filter_by(user_id=current_user.id).all()
    tags = Tags.query.filter_by(user_id=current_user.id).all()
    tags = [tag.name for tag in tags]

    return render_template('livre.html', books=books, students=all_students, nb_page=nb_page, page=int(page), tags=json.dumps(tags))


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
        tags = request.form.get('tags')

        # to avoid empty string (because isbn is a required field)
        if (isbn == ''):
            isbn = None

        if (author == "None"):
            author = ""

        if (editor == "undefined"):
            editor = ""

        if not title:
            flash('Veuillez ajouter un titre.', 'error')
            return redirect(url_for('livre.livre_ajout'))

        tags = tags.split(',')
        tags_in_db = Tags.query.filter_by(user_id=current_user.id).all()
        tags_in_db = [tag.name for tag in tags_in_db]

        # If the tag is not in the database, we add it
        for tag in tags:
            if tag not in tags_in_db:
                new_tag = Tags(name=tag, user_id=current_user.id)
                db.session.add(new_tag)
                db.session.commit()

        # Check if the book already exists
        book = Book.query.filter_by(user_id=current_user.id, title=title).first()
        if book:
            # The book already exists
            flash('Ce titre est déja utilisé pour un autre livre.', 'error')
            return redirect(url_for('livre.livre_ajout'))


        new_book = Book(title=title, author=author, editor=editor, year=year, type=type, isbn=isbn, user_id=current_user.id)
        db.session.add(new_book)

        # Add the tags to the book
        for tag in tags:
            tag_id = Tags.query.filter_by(name=tag, user_id=current_user.id).first().id
            book_tag = BookTags(book_id=new_book.id, tag_id=tag_id)
            db.session.add(book_tag)

        db.session.commit()

        return redirect(url_for('livre.livre_db'))

    # Get all tags (only the name) from the current user
    tags = Tags.query.filter_by(user_id=current_user.id).all()
    tags = [tag.name for tag in tags]

    return render_template('livre_ajout.html', tags=json.dumps(tags))


@livre.route('/livre/scann', methods=['GET', 'POST'])
@login_required
def livre_scann():
    return render_template('livre_scann_live.html')


@livre.route('/livre/<id>/edit', methods=['GET', 'POST'])
@login_required
def livre_edit(id):
    book = Book.query.filter_by(id=id, user_id=current_user.id).first()

    if not book:
        flash('Le livre que vous souhaitiez éditer n\'existe pas.', 'error')
        return redirect(url_for('livre.livre_db'))

    # Get all students from the current user
    students = Student.query.filter_by(user_id=current_user.id).all()
    students = [(student.id, student.name, student.firstname) for student in students]

    loan = Loan.query.filter_by(book_id=id, date_return=None).first()
    student = Student.query.filter_by(id=loan.student_id).first() if loan else None

    tags = Tags.query.filter_by(user_id=current_user.id).all()
    tags = [tag.name for tag in tags]

    book_tags = Tags.query.join(BookTags, Tags.id == BookTags.tag_id).filter(BookTags.book_id == id, Tags.user_id == current_user.id).all()
    book_tags = [tag.name for tag in book_tags]

    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        editor = request.form.get('editor')
        year = request.form.get('year')
        type = request.form.get('type')
        isbn = request.form.get('isbn')
        student = request.form.get('student')
        tags = request.form.get('tags')

        if not title:
            flash('Veuillez ajouter un titre au livre.', 'info')
            return redirect(url_for('livre.livre_edit', id=id))

        if (isbn == ''):
            isbn = None

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

        # Add the tags to the book
        book_tags = BookTags.query.filter_by(book_id=id).all()
        for book_tag in book_tags:
            db.session.delete(book_tag)

        tags = tags.split(',')

        # Get all tags from the current user
        tags_in_db = Tags.query.filter_by(user_id=current_user.id).all()
        tags_in_db = [tag.name for tag in tags_in_db]

        # If the tag is not in the database, we add it
        for tag in tags:
            if tag not in tags_in_db:
                new_tag = Tags(name=tag, user_id=current_user.id)
                db.session.add(new_tag)
                db.session.commit()

            # Add the tags to the book
            tag_id = Tags.query.filter_by(name=tag, user_id=current_user.id).first().id
            book_tag = BookTags(book_id=id, tag_id=tag_id)
            db.session.add(book_tag)

        db.session.commit()

        return redirect(url_for('livre.livre_db'))

    return render_template('livre_edit.html', book=book, students=students, student=student, tags=json.dumps(tags), book_tags=book_tags)

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

@livre.route('/livre/delete_all', methods=['POST'])
@login_required
def livre_delete_all():
    books = Book.query.filter_by(user_id=current_user.id).all()
    for book in books:
        loans = Loan.query.filter_by(book_id=book.id).all()
        for loan in loans:
            db.session.delete(loan)
        db.session.delete(book)

    db.session.commit()

    flash('Tous les livres ont été supprimés.', 'info')

    return redirect(url_for('auth.reglage'))
