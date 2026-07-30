"""
query.py: This file contains all the queries to the database.
"""

from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import aliased
from sqlalchemy.sql import collate

from . import db
from .models import Book, BookTags, Loan, Student, Tags, User

"""
Get all books from a user
    :param current_user_id: the user id
    :return: the list of books
"""


def get_books(current_user_id) -> list:
    books = db.session.query(Book).filter(Book.user_id == current_user_id).all()
    return books


"""
Get the number of books from a user
    :param current_user_id: the user id
    :return: the number of books
"""


def get_books_count(current_user_id) -> int:
    books_count = db.session.query(Book).filter(Book.user_id == current_user_id).count()
    return books_count


def get_books_count_by_title(current_user_id, title) -> int:
    """
    Get the number of books from a user by title
        :param current_user_id: the user id
        :param title: the book title
        :return: the number of books
    """
    books_count = (
        db.session.query(Book)
        .filter(Book.user_id == current_user_id, Book.title == title)
        .count()
    )
    return books_count


"""
Get a book by his id
    :param current_user_id: the user id
    :param book_id: the book id
    :return: the book
"""


def get_book_by_id(current_user_id, book_id) -> Book:
    book = (
        db.session.query(Book)
        .filter(Book.user_id == current_user_id, Book.id == book_id)
        .first()
    )
    return book


"""
Get a book by his isbn
    :param current_user_id: the user id
    :param isbn: the book isbn
    :return: the book
"""


def get_book_by_isbn(current_user_id, isbn) -> Book:
    book = (
        db.session.query(Book)
        .filter(Book.user_id == current_user_id, Book.isbn == isbn)
        .first()
    )
    return book


"""
Get all books by their isbn
    :param current_user_id: the user id
    :param isbn: the book isbn
    :return: a list of books
"""


def get_books_by_isbn(current_user_id, isbn) -> list:
    books = (
        db.session.query(Book)
        .filter(Book.user_id == current_user_id, Book.isbn == isbn)
        .all()
    )
    return books


"""
Get a book by his title
    :param current_user_id: the user id
    :param title: the book title
    :return: the book
"""


def get_book_by_title(current_user_id, title) -> Book:
    book = (
        db.session.query(Book)
        .filter(Book.user_id == current_user_id, Book.title == title)
        .first()
    )
    return book


"""
Get all books and the student who have the book actually
    :param current_user_id: the user id
    :return: the list of books (Book, Student)
"""


def get_books_student(current_user_id, n_par_page, page) -> list:
    books = (
        db.session.query(Book, Student)
        .filter(Book.user_id == current_user_id)
        .outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return.is_(None)))
        .outerjoin(Student, Loan.student_id == Student.id)
        .limit(n_par_page)
        .offset((page - 1) * n_par_page)
        .all()
    )
    return books


"""
Get all books with the tags and the student who have the book actually
The tags and the count of loans are also returned
    :param current_user_id: the user id
    :return: the list of books (Book, Student, tags, loan_count)
"""


def get_books_student_tags(current_user_id, n_par_page, page) -> list:
    subquery_tags = (
        db.session.query(
            BookTags.book_id, func.group_concat(Tags.name, ",").label("tags")
        )
        .join(Tags, BookTags.tag_id == Tags.id)
        .group_by(BookTags.book_id)
        .subquery()
    )

    subquery_loan_count = (
        db.session.query(Loan.book_id, func.count(Loan.id).label("loan_count"))
        .group_by(Loan.book_id)
        .subquery()
    )

    books = (
        db.session.query(
            Book,
            Student,
            subquery_tags.c.tags,
            func.coalesce(subquery_loan_count.c.loan_count, 0).label("loan_count"),
        )
        .filter(Book.user_id == current_user_id)
        .outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return.is_(None)))
        .outerjoin(Student, Loan.student_id == Student.id)
        .outerjoin(subquery_tags, Book.id == subquery_tags.c.book_id)
        .outerjoin(subquery_loan_count, Book.id == subquery_loan_count.c.book_id)
        .limit(n_par_page)
        .offset((page - 1) * n_par_page)
        .all()
    )

    return books


"""
Get all students
    :param current_user_id: the user id
    :return: the list of students
"""


def get_students(current_user_id) -> list:
    students = (
        db.session.query(Student).filter(Student.user_id == current_user_id).all()
    )
    return students


"""
Get the number of students
    :param current_user_id: the user id
    :return: the number of students
"""


def get_students_count(current_user_id) -> int:
    students_count = (
        db.session.query(Student).filter(Student.user_id == current_user_id).count()
    )
    return students_count


"""
Get the student by his id
    :param current_user_id: the user id
    :param student_id: the student id
    :return: the student
"""


def get_student_by_id(current_user_id, student_id) -> Student:
    student = (
        db.session.query(Student)
        .filter(Student.user_id == current_user_id, Student.id == student_id)
        .first()
    )
    return student


"""
Get all students with the number of loans and the last loan date
    :param current_user_id: the user id
    :return: the list of students
"""


def get_all_students_info(current_user_id) -> list:
    subquery_loan_count = (
        db.session.query(Loan.student_id, func.count(Loan.id).label("loan_count"))
        .group_by(Loan.student_id)
        .subquery()
    )

    last_loan_subquery = (
        db.session.query(Loan.student_id, func.max(Loan.date_loan).label("last_loan"))
        .group_by(Loan.student_id)
        .subquery()
    )

    last_loan_alias = aliased(Loan, last_loan_subquery)

    students = (
        db.session.query(
            Student,
            Book,
            last_loan_subquery.c.last_loan,
            func.coalesce(subquery_loan_count.c.loan_count, 0).label("loan_count"),
        )
        .filter(Student.user_id == current_user_id)
        .outerjoin(
            Loan, and_(Student.id == Loan.student_id, Loan.date_return.is_(None))
        )
        .outerjoin(Book, Loan.book_id == Book.id)
        .outerjoin(last_loan_alias, Student.id == last_loan_alias.student_id)
        .outerjoin(subquery_loan_count, Student.id == subquery_loan_count.c.student_id)
        .group_by(Student.id)
        .order_by(collate(Student.name, "NOCASE"), collate(Student.firstname, "NOCASE"))
        .all()
    )

    return students


def get_search_all_students_info(current_user_id, search) -> list:
    subquery_loan_count = (
        db.session.query(Loan.student_id, func.count(Loan.id).label("loan_count"))
        .group_by(Loan.student_id)
        .subquery()
    )

    last_loan_subquery = (
        db.session.query(Loan.student_id, func.max(Loan.date_loan).label("last_loan"))
        .group_by(Loan.student_id)
        .subquery()
    )

    last_loan_alias = aliased(Loan, last_loan_subquery)

    students = (
        db.session.query(
            Student,
            Book,
            last_loan_subquery.c.last_loan,
            func.coalesce(subquery_loan_count.c.loan_count, 0).label("loan_count"),
        )
        .filter(
            and_(
                Student.user_id == current_user_id,
                or_(
                    Student.name.like("%" + search + "%"),
                    Student.firstname.like("%" + search + "%"),
                ),
            )
        )
        .outerjoin(
            Loan, and_(Student.id == Loan.student_id, Loan.date_return.is_(None))
        )
        .outerjoin(Book, Loan.book_id == Book.id)
        .outerjoin(last_loan_alias, Student.id == last_loan_alias.student_id)
        .outerjoin(subquery_loan_count, Student.id == subquery_loan_count.c.student_id)
        .group_by(Student.id)
        .order_by(collate(Student.name, "NOCASE"), collate(Student.firstname, "NOCASE"))
        .all()
    )

    return students


"""
Get one student by his id with the list of actual loans and the list of old loans
    :param current_user_id: the user id
    :param student_id: the student id
    :return: the student, the list of actual loans, the list of old loans
"""


def get_student_infos(current_user_id, student_id) -> (Student, list, list):
    # Query to get the student
    student = (
        db.session.query(Student)
        .filter(Student.user_id == current_user_id, Student.id == student_id)
        .first()
    )

    # Query to get the current loans
    current_loans = (
        db.session.query(Loan, Book)
        .filter(
            Book.user_id == current_user_id,
            Loan.student_id == student_id,
            Loan.date_return.is_(None),
        )
        .join(Book, Loan.book_id == Book.id)
        .all()
    )

    # Query to get the past loans
    past_loans = (
        db.session.query(Loan, Book)
        .filter(
            Book.user_id == current_user_id,
            Loan.student_id == student_id,
            Loan.date_return.is_not(None),
        )
        .join(Book, Loan.book_id == Book.id)
        .all()
    )

    return student, current_loans, past_loans


"""
Get all the loans
    :param current_user_id: the user id
    :return: the list of loans
"""


def get_loans(current_user_id) -> list:
    loans = db.session.query(Loan).filter(Loan.user_id == current_user_id).all()
    return loans


"""
Get the number of loans
    :param current_user_id: the user id
    :return: the number of loans
"""


def get_loans_count(current_user_id) -> int:
    loans_count = (
        db.session.query(Loan)
        .filter(Book.user_id == current_user_id)
        .outerjoin(Book, Loan.book_id == Book.id)
        .count()
    )
    return loans_count


"""
Get loans with the book and the student
    :param current_user_id: the user id
    :param actualy_loan: if True, only the actual loans are returned
    :return: the list of loans (Loan, Book, Student)
"""


def get_loans_with_infos(
    current_user_id,
    actualy_loan=False,
    sort="Loan.id",
    sort_order="asc",
    n_books_by_page=10,
    page=1,
):
    query = db.session.query(Loan, Book, Student).filter(
        Book.user_id == current_user_id
    )

    if actualy_loan:
        query = query.filter(Loan.date_return.is_(None))

    query = query.join(Book, Loan.book_id == Book.id).join(
        Student, Loan.student_id == Student.id
    )

    query = query.order_by(
        collate(text(sort), "NOCASE").desc()
        if sort_order == "desc"
        else collate(text(sort), "NOCASE")
    )

    n_books = query.count()

    loans_with_infos = (
        query.limit(n_books_by_page).offset((page - 1) * n_books_by_page).all()
    )

    return loans_with_infos, n_books


def get_loans_with_infos_bookid(current_user_id, book_id, actualy_loan=False) -> list:
    query = db.session.query(Loan, Book, Student).filter(
        Book.user_id == current_user_id, Book.id == book_id
    )

    if actualy_loan:
        query = query.filter(Loan.date_return.is_(None))
    else:
        query = query.filter(Loan.date_return.is_not(None))
        query = query.order_by(Loan.date_loan.desc(), Loan.date_return.desc())

    query = query.join(Book, Loan.book_id == Book.id).join(
        Student, Loan.student_id == Student.id
    )

    if actualy_loan:
        loans_with_infos = query.first()
    else:
        loans_with_infos = query.all()

    return loans_with_infos


"""
Get the actual loan from a book
    :param current_user_id: the user id
    :param book_id: the book id
    :return: the loan
"""


def get_book_actual_loan(current_user_id, book_id) -> Loan:
    book_loan = (
        db.session.query(Loan)
        .filter(
            Loan.book_id == book_id,
            Loan.date_return.is_(None),
            Book.user_id == current_user_id,
        )
        .join(Book, Loan.book_id == Book.id)
        .first()
    )
    return book_loan


"""
Get all the loans from a book
    :param current_user_id: the user id
    :param book_id: the book id
    :return: the list of loans
"""


def get_book_loans(current_user_id, book_id) -> list:
    book_loans = (
        db.session.query(Loan)
        .filter(Loan.book_id == book_id, Book.user_id == current_user_id)
        .join(Book, Loan.book_id == Book.id)
        .all()
    )
    return book_loans


"""
Get the student who have the book actually
    :param current_user_id: the user id
    :param book_id: the book id
    :return: the student
"""


def get_book_loan_by_student(current_user_id, book_id) -> Student:
    student = (
        db.session.query(Student)
        .join(Loan)
        .filter(
            Student.user_id == current_user_id,
            Loan.book_id == book_id,
            Loan.date_return.is_(None),
        )
        .first()
    )
    return student


"""
Get all the tags
    :param current_user_id: the user id
    :return: the list of tags
"""


def get_tags(current_user_id) -> list:
    tags = db.session.query(Tags).filter(Tags.user_id == current_user_id).all()
    return tags


"""
Get user information
    :param current_user_id: the user id
    :return: the user (id, email, name)
"""


def get_user(current_user_id) -> list:
    user = (
        db.session.query(User.id, User.email, User.name)
        .filter(User.id == current_user_id)
        .first()
    )
    return user


"""
Get tags from a book
    :param current_user_id: the user id
    :param book_id: the book id
    :return: the list of tags
"""


def get_book_tags(current_user_id, book_id) -> list:
    book_tags = (
        db.session.query(Tags)
        .join(BookTags)
        .join(Book)
        .filter(Book.user_id == current_user_id, Book.id == book_id)
        .all()
    )
    return book_tags


"""
Get the book most borrowed
    :param current_user_id: the user id
    :param n_books: the number of books to return (5)
    :return: the list of books (Book, loan_count)
"""


def get_books_most_borrowed(current_user_id, n_books=5) -> list:
    subquery_loan_count = (
        db.session.query(Loan.book_id, func.count(Loan.id).label("loan_count"))
        .group_by(Loan.book_id)
        .subquery()
    )

    books = (
        db.session.query(
            Book, func.coalesce(subquery_loan_count.c.loan_count, 0).label("loan_count")
        )
        .filter(Book.user_id == current_user_id)
        .outerjoin(subquery_loan_count, Book.id == subquery_loan_count.c.book_id)
        .order_by(subquery_loan_count.c.loan_count.desc())
        .limit(n_books)
        .all()
    )

    return books


"""
Get the student who read the most books
    :param current_user_id: the user id
    :param n_students: the number of students to return (5)
    :return: the list of students (Student, loan_count)
"""


def get_students_most_borrowed(current_user_id, n_students=5) -> list:
    subquery_loan_count = (
        db.session.query(Loan.student_id, func.count(Loan.id).label("loan_count"))
        .group_by(Loan.student_id)
        .subquery()
    )

    students = (
        db.session.query(
            Student,
            func.coalesce(subquery_loan_count.c.loan_count, 0).label("loan_count"),
        )
        .filter(Student.user_id == current_user_id)
        .outerjoin(subquery_loan_count, Student.id == subquery_loan_count.c.student_id)
        .order_by(subquery_loan_count.c.loan_count.desc())
        .limit(n_students)
        .all()
    )

    return students


"""
Get the last book loan or return
    :param current_user_id: the user id
    :param n_books: the number of books to return (5)
    :return: the list of books (Book, Loan, Student)
"""


def get_last_book_loan(current_user_id, n_books=5) -> list:
    books = (
        db.session.query(Book, Loan, Student)
        .filter(Book.user_id == current_user_id)
        .join(Loan, and_(Book.id == Loan.book_id))
        .join(Student, Loan.student_id == Student.id)
        .order_by(Loan.date_loan.desc())
        .limit(n_books)
        .all()
    )

    return books


"""
Get the number of loan over the last year grouped for each 4 weeks (1 month)
Exemple of result: ('2024-01', 2), ('2024-02', 3), ('2024-03', 1)
    :param current_user_id: the user id
    :return: the list of loans
"""


def get_loans_over_the_year(current_user_id) -> list:
    # Generate a list of 365 days
    today = datetime.today()

    # Le nombre de jour est 365 + le jour de la semaine pour que notre graphique soit correctement aligné.
    # 52 * 7 = 364, la colonne 53 est la semaine en cours.
    # Donc 365 est lundi actuel. On peut ensuite ajouter le jour de la semaine - 2.
    number_of_day = 365 + int(today.strftime("%w")) - 2

    start_date = today - timedelta(days=number_of_day)
    days = [
        (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(0, number_of_day + 1)
    ]

    # Query to get loans per day
    loans = (
        db.session.query(
            func.strftime("%Y-%m-%d", Loan.date_loan).label("year_day"),
            func.count(Loan.id).label("loan_count"),
        )
        .filter(
            Book.user_id == current_user_id,
            Loan.date_loan > func.date("now", f"-{number_of_day} days"),
        )
        .join(Book, Loan.book_id == Book.id)
        .group_by("year_day")
        .all()
    )

    returns = (
        db.session.query(
            func.strftime("%Y-%m-%d", Loan.date_return).label("year_day"),
            func.count(Loan.id).label("return_count"),
        )
        .filter(
            Book.user_id == current_user_id,
            Loan.date_return > func.date("now", f"-{number_of_day} days"),
        )
        .join(Book, Loan.book_id == Book.id)
        .group_by("year_day")
        .all()
    )

    combined = {day: {"loan_count": 0, "return_count": 0} for day in days}

    for loan in loans:
        combined[loan.year_day]["loan_count"] = loan.loan_count

    for r in returns:
        combined[r.year_day]["return_count"] = r.return_count

    result = [
        (
            datetime.strptime(day, "%Y-%m-%d"),
            combined[day]["loan_count"],
            combined[day]["return_count"],
        )
        for day in days
    ]

    return result


"""
Get the 5 books that match the search (title, isbn, student name, student firstname)
    :param current_user_id: the user id
    :param search: the search string
    :return: the list of books
"""


def get_search_5_books(current_user_id, search) -> list:
    books = (
        db.session.query(Book, Loan, Student)
        .filter(
            Book.user_id == current_user_id,
            or_(
                Book.title.ilike("%" + search + "%"),
                Book.isbn.ilike("%" + search + "%"),
                Student.name.ilike("%" + search + "%"),
                Student.firstname.ilike("%" + search + "%"),
            ),
        )
        .outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return.is_(None)))
        .outerjoin(Student, Loan.student_id == Student.id)
        .limit(5)
        .all()
    )
    return books


"""
Get all the books, sorted.
    :param current_user_id: the user id
    :param sort: the column to sort (Book.id)
    :param sort_order: the order to sort (asc, desc)
    :param n_par_page: the number of elements per page (10)
    :param page: the page number (1)
    :return: the list of books
"""


def get_books_sorted(
    current_user_id, sort="Book.id", sort_order="asc", n_par_page=10, page=1
) -> list:
    subquery_tags = (
        db.session.query(
            BookTags.book_id, func.group_concat(Tags.name, ",").label("tags")
        )
        .join(Tags, BookTags.tag_id == Tags.id)
        .group_by(BookTags.book_id)
        .subquery()
    )

    subquery_loan_count = (
        db.session.query(Loan.book_id, func.count(Loan.id).label("loan_count"))
        .group_by(Loan.book_id)
        .subquery()
    )

    books = (
        db.session.query(
            Book,
            Student,
            subquery_tags.c.tags,
            func.coalesce(subquery_loan_count.c.loan_count, 0).label("loan_count"),
        )
        .filter(Book.user_id == current_user_id)
        .outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return.is_(None)))
        .outerjoin(Student, Loan.student_id == Student.id)
        .outerjoin(subquery_tags, Book.id == subquery_tags.c.book_id)
        .outerjoin(subquery_loan_count, Book.id == subquery_loan_count.c.book_id)
        .order_by(
            collate(text(sort), "NOCASE").desc()
            if sort_order == "desc"
            else collate(text(sort), "NOCASE")
        )
        .limit(n_par_page)
        .offset((page - 1) * n_par_page)
    )

    return books


"""
Get the books that match the search
    :param current_user_id: the user id
    :param search_type: the search type (titre, isbn, eleve, tags, all)
    :param search_value: the search value
    :param sort: the column to sort (Book.id, ...)
    :param sort_order: the order to sort (asc, desc)
    :param n_books_by_page: the number of elements per page
    :param page: the page number
    :return: the list of books (Book, Student, tags, loan_count)
"""


def search_books_by_types(
    current_user_id, search_type, search_value, sort, sort_order, n_books_by_page, page
):
    subquery_tags = (
        db.session.query(
            BookTags.book_id, func.group_concat(Tags.name, ",").label("tags")
        )
        .join(Tags, BookTags.tag_id == Tags.id)
        .group_by(BookTags.book_id)
        .subquery()
    )

    subquery_loan_count = (
        db.session.query(Loan.book_id, func.count(Loan.id).label("loan_count"))
        .group_by(Loan.book_id)
        .subquery()
    )

    query = db.session.query(
        Book,
        Student,
        subquery_tags.c.tags,
        func.coalesce(subquery_loan_count.c.loan_count, 0).label("loan_count"),
    )
    query = query.filter(Book.user_id == current_user_id)
    query = query.outerjoin(
        Loan, and_(Book.id == Loan.book_id, Loan.date_return.is_(None))
    )
    query = query.outerjoin(Student, Loan.student_id == Student.id)
    query = query.outerjoin(subquery_tags, Book.id == subquery_tags.c.book_id)
    query = query.outerjoin(
        subquery_loan_count, Book.id == subquery_loan_count.c.book_id
    )

    if search_type == "titre":
        query = query.filter(Book.title.ilike("%" + search_value + "%"))
    elif search_type == "isbn":
        query = query.filter(Book.isbn.ilike("%" + search_value + "%"))
    elif search_type == "eleve":
        query = query.filter(
            or_(
                Student.name.ilike("%" + search_value + "%"),
                Student.firstname.ilike("%" + search_value + "%"),
            )
        )
    elif search_type == "tags":
        query = query.outerjoin(BookTags, Book.id == BookTags.book_id)
        query = query.outerjoin(Tags, BookTags.tag_id == Tags.id)
        query = query.filter(Tags.name.ilike("%" + search_value + "%"))
    elif search_type == "all":
        query = query.outerjoin(BookTags, Book.id == BookTags.book_id)
        query = query.outerjoin(Tags, BookTags.tag_id == Tags.id)
        query = query.filter(
            or_(
                Book.title.ilike("%" + search_value + "%"),
                Book.isbn.ilike("%" + search_value + "%"),
                Student.name.ilike("%" + search_value + "%"),
                Student.firstname.ilike("%" + search_value + "%"),
                Tags.name.ilike("%" + search_value + "%"),
            )
        )

    query = query.order_by(
        collate(text(sort), "NOCASE").desc()
        if sort_order == "desc"
        else collate(text(sort), "NOCASE")
    )

    n_books = query.count()

    books = query.limit(n_books_by_page).offset((page - 1) * n_books_by_page).all()

    return books, n_books


"""
Get the 5 loans that match the search (title, isbn, student name, student firstname)
    :param current_user_id: the user id
    :param search: the search string
    :return: the list of books
"""


def get_search_5_loans(current_user_id, search) -> list:
    books = (
        db.session.query(Loan, Book, Student)
        .filter(
            Book.user_id == current_user_id,
            or_(
                Book.title.ilike("%" + search + "%"),
                Book.isbn.ilike("%" + search + "%"),
                Student.name.ilike("%" + search + "%"),
                Student.firstname.ilike("%" + search + "%"),
            ),
        )
        .join(Book, Loan.book_id == Book.id)
        .join(Student, Loan.student_id == Student.id)
        .limit(5)
        .all()
    )
    return books


"""
Get the loans that match the search
    :param current_user_id: the user id
    :param actualy_loan: if True, only the actual loans are returned
    :param search_type: the search type (titre, isbn, eleve, tags, all)
    :param search_value: the search value
    :param sort: the column to sort (Book.id, ...)
    :param sort_order: the order to sort (asc, desc)
    :param n_books_by_page: the number of elements per page
    :param page: the page number
    :return: the list of books (Book, Student, tags, loan_count)
"""


def search_loans_by_types(
    current_user_id,
    actualy_loan,
    search_type,
    search_value,
    sort,
    sort_order,
    n_books_by_page,
    page,
):
    query = db.session.query(Loan, Book, Student).filter(
        Book.user_id == current_user_id
    )

    if actualy_loan:
        query = query.filter(Loan.date_return.is_(None))

    query = query.join(Book, Loan.book_id == Book.id).join(
        Student, Loan.student_id == Student.id
    )

    if search_type == "titre":
        query = query.filter(Book.title.ilike("%" + search_value + "%"))
    elif search_type == "isbn":
        query = query.filter(Book.isbn.ilike("%" + search_value + "%"))
    elif search_type == "eleve":
        query = query.filter(
            or_(
                Student.name.ilike("%" + search_value + "%"),
                Student.firstname.ilike("%" + search_value + "%"),
            )
        )
    elif search_type == "tags":
        query = query.outerjoin(BookTags, Book.id == BookTags.book_id)
        query = query.outerjoin(Tags, BookTags.tag_id == Tags.id)
        query = query.filter(Tags.name.ilike("%" + search_value + "%"))
    elif search_type == "all":
        query = query.outerjoin(BookTags, Book.id == BookTags.book_id)
        query = query.outerjoin(Tags, BookTags.tag_id == Tags.id)
        query = query.filter(
            or_(
                Book.title.ilike("%" + search_value + "%"),
                Book.isbn.ilike("%" + search_value + "%"),
                Student.name.ilike("%" + search_value + "%"),
                Student.firstname.ilike("%" + search_value + "%"),
                Tags.name.ilike("%" + search_value + "%"),
            )
        )

    query = query.order_by(
        collate(text(sort), "NOCASE").desc()
        if sort_order == "desc"
        else collate(text(sort), "NOCASE")
    )

    n_books = query.count()

    books = query.limit(n_books_by_page).offset((page - 1) * n_books_by_page).all()

    return books, n_books


"""
Get infos about the app
    :return: (n of users, n of books, n of student, n of loan)
"""


def get_app_infos():
    infos = {
        "n_users": db.session.query(User).count(),
        "n_books": db.session.query(Book).count(),
        "n_students": db.session.query(Student).count(),
        "n_loans": db.session.query(Loan).count(),
    }

    return infos


def get_books_read_by_students(current_user_id, date_from, date_to):
    """
    Retourne le nombre de livres lus par élève entre deux dates (incluses).
    :param current_user_id: l'id de l'utilisateur
    :param date_from: date de début (string 'YYYY-MM-DD')
    :param date_to: date de fin (string 'YYYY-MM-DD')
    :return: liste de tuples (nom complet, nombre de livres lus)
    """
    from datetime import datetime

    from sqlalchemy import func

    from .models import Loan, Student

    # Conversion des dates
    try:
        date_from = datetime.strptime(date_from, "%Y-%m-%d")
        date_to = datetime.strptime(date_to, "%Y-%m-%d")
    except Exception:
        return []

    # Requête : inclure tous les élèves, même sans emprunt
    results = (
        db.session.query(
            (Student.name + " " + Student.firstname).label("fullname"),
            func.coalesce(func.count(Loan.id), 0).label("books_read"),
        )
        .outerjoin(Loan, Loan.student_id == Student.id)
        .filter(Student.user_id == current_user_id)
        .filter(
            (Loan.date_loan >= date_from) & (Loan.date_loan <= date_to)
            | (Loan.id.is_(None))
        )
        .group_by(Student.id)
        .order_by(func.count(Loan.id).desc())
        .all()
    )
    return results
