# main.py

from flask import Blueprint, render_template, redirect, url_for, request, flash, make_response
from flask_login import login_required, current_user

import cv2
import numpy as np
from pyzbar.pyzbar import decode
import isbnlib

from .models import Book, Student, Loan
from . import db

livre = Blueprint('livre', __name__)

@livre.route('/livre')
@login_required
def livre_db():
    # Take all books from the current user
    #books = Book.query.filter_by(user_id=current_user.id).all()
    #books = [book for book in books]

    # Query books and add the student name if the book is loaned
    books_with_loans = db.session.query(Book, Loan, Student).filter(Book.user_id == current_user.id).outerjoin(Loan, Book.id == Loan.book_id).outerjoin(Student, Loan.student_id == Student.id).all()

    books = [(book, student) for (book, _, student) in books_with_loans]
    print(books)

    return render_template('livre.html', books=books)


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
    if request.method == 'POST':
        title = request.form.get('title')
        isbn = request.form.get('isbn')

        if not isbn:
            flash('Veuillez scanner un livre.')
            return redirect(url_for('livre.livre_scann'))

    return render_template('livre_scann.html')


def send_file_data(data, mimetype='image/jpeg', filename='output.jpg'):
    # https://stackoverflow.com/questions/11017466/flask-to-return-image-stored-in-database/11017839

    response = make_response(data)
    response.headers.set('Content-Type', mimetype)
    response.headers.set('Content-Disposition', 'attachment', filename=filename)

    return response


@livre.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        # fs = request.files['snap'] # it raise error when there is no `snap` in form
        fs = request.files.get('snap')
        if fs:
            # print('FileStorage:', fs)
            print('filename:', fs.filename)

            # https://stackoverflow.com/questions/27517688/can-an-uploaded-image-be-loaded-directly-by-cv2
            # https://stackoverflow.com/a/11017839/1832058
            img = cv2.imdecode(np.frombuffer(fs.read(), np.uint8), cv2.IMREAD_UNCHANGED)

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            code = decode(gray)

            if code:
                try:
                    isbnlib.meta(code[0].data.decode('utf8'))
                    # gray = cv2.rectangle(gray, code[0].rect, (0, 255, 0), 3)
                    # gray = cv2.putText(gray, code[0].data.decode('utf8'), (code[0].rect[0], code[0].rect[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 3)
                    meta = isbnlib.meta(code[0].data.decode('utf8'))
                    print(meta)
                    ret, buf = cv2.imencode('.jpg', gray)
                    send_file_data(buf.tobytes())
                except Exception as e:
                    flash('ISBN not found')

            # https://jdhao.github.io/2019/07/06/python_opencv_pil_image_to_bytes/
            # ret, buf = cv2.imencode('.jpg', img)

            # return f'Got Snap! {img.shape}'
            # return send_file_data(buf.tobytes())
        else:
            return 'You forgot Snap!'

    return 'Hello World!'


@livre.route('/livre/<id>/edit', methods=['GET', 'POST'])
@login_required
def livre_edit(id):
    book = Book.query.filter_by(id=id).first()
    # Check if the book belongs to the current user
    if book.user_id != current_user.id:
        flash('Vous ne pouvez pas modifier ce livre.')
        return redirect(url_for('livre.livre_db'))

    # Get all students from the current user
    students = Student.query.filter_by(user_id=current_user.id).all()
    students = [(student.id, student.name, student.firstname) for student in students]

    loan = Loan.query.filter_by(book_id=id).first()
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
        student = Student.query.filter_by(id=student).first()

        if student:
            loan = Loan.query.filter_by(book_id=id).first()
            if loan:
                # Update the loan
                loan.student_id = student.id
            else:
                new_loan = Loan(student_id=student.id, book_id=id)
                print(new_loan)
                db.session.add(new_loan)
        else:
            loan = Loan.query.filter_by(book_id=id).first()
            if loan:
                db.session.delete(loan)

        db.session.commit()

        return redirect(url_for('livre.livre_db'))

    return render_template('livre_edit.html', book=book, students=students, student=student)

@livre.route('/livre/<id>/delete')
@login_required
def livre_delete(id):
    book = Book.query.filter_by(id=id).first()
    db.session.delete(book)
    db.session.commit()

    return redirect(url_for('livre.livre_db'))