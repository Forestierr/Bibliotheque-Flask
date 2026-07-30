# models.py
# look at the file docs/model.png

import os

from flask_login import UserMixin
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

from . import db

# Table d'association pour la relation Many-to-Many entre Book et Tags


class BookTags(db.Model):
    __tablename__ = "book_tags"
    book_id = db.Column(db.Integer, db.ForeignKey("book.id"), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey("tags.id"), primary_key=True)


class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(1000))
    is_verified = db.Column(db.Boolean, default=False)

    # One-to-Many relationship with books
    books = relationship("Book", backref="user", lazy=True)  # User can have many books
    # One-to-Many relationship with students
    students = relationship(
        "Student", backref="user", lazy=True
    )  # User can have many students
    # One-to-Many relationship with tags
    tags = relationship("Tags", backref="user", lazy=True)  # User can have many tags

    def get_verification_token(self):
        serializer = URLSafeTimedSerializer(os.getenv("SECRET_KEY"))
        return serializer.dumps(self.email, salt="email-verify-" + self.password)

    @staticmethod
    def validate_verification_token(token: str, user_id: int):
        user = User.query.get(user_id)

        if not user:
            return None

        serializer = URLSafeTimedSerializer(os.getenv("SECRET_KEY"))
        try:
            email = serializer.loads(
                token,
                salt="email-verify-" + user.password,
                max_age=86400,  # Token valid for 24 hours
            )
        except Exception:
            return None

        if email != user.email:
            return None

        return user

    def get_reset_password_token(self):
        serializer = URLSafeTimedSerializer(os.getenv("SECRET_KEY"))
        return serializer.dumps(self.email, salt=self.password)

    @staticmethod
    def validate_reset_password_token(token: str, user_id: int):
        user = User.query.get(user_id)

        if not user:
            return None

        serializer = URLSafeTimedSerializer(os.getenv("SECRET_KEY"))
        try:
            email = serializer.loads(
                token, salt=user.password, max_age=3600
            )  # Token valid for 1 hour
        except Exception:
            return None

        if email != user.email:
            return None

        return user


class Book(db.Model):
    __tablename__ = "book"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    author = db.Column(db.String(100))
    editor = db.Column(db.String(100))
    year = db.Column(db.Integer)
    type = db.Column(db.String(100))
    isbn = db.Column(db.String(100), nullable=True)

    user_id = db.Column(
        db.Integer, ForeignKey("user.id")
    )  # Each book belongs to a user
    loans = relationship(
        "Loan", backref="book", lazy=True, cascade="all, delete-orphan"
    )
    book_tags = relationship(
        "BookTags", backref="book", lazy=True, cascade="all, delete-orphan"
    )


class Student(db.Model):
    __tablename__ = "student"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    firstname = db.Column(db.String(100))

    # Many-to-One relationship with User
    user_id = db.Column(
        db.Integer, ForeignKey("user.id")
    )  # Each student belongs to a user
    # Loan relationship: One student can have multiple loans
    loans = relationship(
        "Loan", backref="student", lazy=True, cascade="all, delete-orphan"
    )


class Loan(db.Model):
    __tablename__ = "loan"
    id = db.Column(db.Integer, primary_key=True)
    date_loan = db.Column(db.Date)
    date_return = db.Column(db.Date)

    # Foreign keys to link Student and Book
    student_id = db.Column(db.Integer, ForeignKey("student.id"), nullable=False)
    book_id = db.Column(db.Integer, ForeignKey("book.id"), nullable=False)


class Tags(db.Model):
    __tablename__ = "tags"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))

    user_id = db.Column(db.Integer, ForeignKey("user.id"), nullable=False)
    book_tags = relationship(
        "BookTags", backref="tag", lazy=True, cascade="all, delete-orphan"
    )
