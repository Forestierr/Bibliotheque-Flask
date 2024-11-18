# models.py
# look at the file docs/model.png

from flask_login import UserMixin
from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from . import db

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(1000))

    # One-to-Many relationship with books
    books = relationship('Book', backref='user', lazy=True)  # User can have many books
    # One-to-Many relationship with students
    students = relationship('Student', backref='user', lazy=True)  # User can have many students

class Book(db.Model):
    __tablename__ = 'book'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), unique=True)
    author = db.Column(db.String(100))
    editor = db.Column(db.String(100))
    year = db.Column(db.Integer)
    type = db.Column(db.String(100))
    isbn = db.Column(db.String(100), unique=True, nullable=True)

    # Many-to-One relationship with User
    user_id = db.Column(db.Integer, ForeignKey('user.id'))  # Each book belongs to a user

    # Loan relationship: One book can be loaned out many times
    loans = relationship('Loan', backref='book', lazy=True)


class Student(db.Model):
    __tablename__ = 'student'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    firstname = db.Column(db.String(100))

    # Many-to-One relationship with User
    user_id = db.Column(db.Integer, ForeignKey('user.id'))  # Each student belongs to a user
    # Loan relationship: One student can have multiple loans
    loans = relationship('Loan', backref='student', lazy=True)


class Loan(db.Model):
    __tablename__ = 'loan'
    id = db.Column(db.Integer, primary_key=True)

    # Foreign keys to link Student and Book
    student_id = db.Column(db.Integer, ForeignKey('student.id'), nullable=False)
    book_id = db.Column(db.Integer, ForeignKey('book.id'), nullable=False)

    date_loan = db.Column(db.Date)
    date_return = db.Column(db.Date)
