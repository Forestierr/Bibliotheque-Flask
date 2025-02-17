from datetime import datetime, timedelta
from sqlalchemy import or_, and_, text, DateTime, func
from sqlalchemy.orm import joinedload, aliased, subqueryload
from sqlalchemy.sql import collate

from .models import User, Book, Student, Loan, Tags, BookTags
from . import db


def get_books(current_user_id) -> list:
    books = db.session.query(Book).filter(Book.user_id == current_user_id).all()
    return books


def get_books_count(current_user_id) -> int:
    books_count = db.session.query(Book).filter(Book.user_id == current_user_id).count()
    return books_count


def get_book_by_id(current_user_id, book_id) -> Book:
    book = db.session.query(Book).filter(Book.user_id == current_user_id, Book.id == book_id).first()
    return book


def get_book_by_isbn(current_user_id, isbn) -> Book:
    book = db.session.query(Book).filter(Book.user_id == current_user_id, Book.isbn == isbn).first()
    return book


def get_books_student(current_user_id) -> list:
    books = (db.session.query(Book, Student)
             .filter(Book.user_id == current_user_id)
             .outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return == None))
             .outerjoin(Student, Loan.student_id == Student.id)
             .all())
    return books


def get_books_student(current_user_id, n_par_page, page) -> list:
    books = (db.session.query(Book, Student)
             .filter(Book.user_id == current_user_id)
             .outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return == None))
             .outerjoin(Student, Loan.student_id == Student.id)
             .limit(n_par_page).offset((page - 1) * n_par_page)
             .all())
    return books


def get_books_student_tags(current_user_id) -> list:
    subquery_tags = (db.session.query(BookTags.book_id, func.group_concat(Tags.name, ',').label('tags'))
                .join(Tags, BookTags.tag_id == Tags.id)
                .group_by(BookTags.book_id)
                .subquery())

    subquery_loan_count = (db.session.query(Loan.book_id, func.count(Loan.id).label('loan_count'))
                            .group_by(Loan.book_id)
                            .subquery())

    books = (db.session.query(Book, Student, subquery_tags.c.tags, func.coalesce(subquery_loan_count.c.loan_count, 0).label('loan_count'))
             .filter(Book.user_id == current_user_id)
             .outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return == None))
             .outerjoin(Student, Loan.student_id == Student.id)
             .outerjoin(subquery_tags, Book.id == subquery_tags.c.book_id)
             .outerjoin(subquery_loan_count, Book.id == subquery_loan_count.c.book_id)
             .all())

    return books


def get_books_student_tags(current_user_id, n_par_page, page) -> list:
    subquery_tags = (db.session.query(BookTags.book_id, func.group_concat(Tags.name, ',').label('tags'))
                .join(Tags, BookTags.tag_id == Tags.id)
                .group_by(BookTags.book_id)
                .subquery())

    subquery_loan_count = (db.session.query(Loan.book_id, func.count(Loan.id).label('loan_count'))
                            .group_by(Loan.book_id)
                            .subquery())

    books = (db.session.query(Book, Student, subquery_tags.c.tags, func.coalesce(subquery_loan_count.c.loan_count, 0).label('loan_count'))
             .filter(Book.user_id == current_user_id)
             .outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return == None))
             .outerjoin(Student, Loan.student_id == Student.id)
             .outerjoin(subquery_tags, Book.id == subquery_tags.c.book_id)
             .outerjoin(subquery_loan_count, Book.id == subquery_loan_count.c.book_id)
             .limit(n_par_page).offset((page - 1) * n_par_page))

    return books


"""
Get all students
    :param current_user_id: the user id
    :return: the list of students
"""
def get_students(current_user_id) -> list:
    students = db.session.query(Student).filter(Student.user_id == current_user_id).all()
    return students


"""
Get the number of students
    :param current_user_id: the user id
    :return: the number of students
"""
def get_students_count(current_user_id) -> int:
    students_count = db.session.query(Student).filter(Student.user_id == current_user_id).count()
    return students_count


"""
Get the student by his id
    :param current_user_id: the user id
    :param student_id: the student id
    :return: the student
"""
def get_student_by_id(current_user_id, student_id) -> Student:
    student = db.session.query(Student).filter(Student.user_id == current_user_id, Student.id == student_id).first()
    return student


"""
Get all students with the number of loans and the last loan date
    :param current_user_id: the user id
    :return: the list of students
"""
def get_all_students_info(current_user_id) -> list:
    subquery_loan_count = (db.session.query(Loan.student_id, func.count(Loan.id).label('loan_count'))
                           .group_by(Loan.student_id)
                           .subquery())

    last_loan_subquery = (db.session.query(Loan.student_id, func.max(Loan.date_loan).label('last_loan'))
                          .group_by(Loan.student_id)
                          .subquery())

    last_loan_alias = aliased(Loan, last_loan_subquery)

    students = (db.session.query(Student, Book, last_loan_subquery.c.last_loan, func.coalesce(subquery_loan_count.c.loan_count, 0).label('loan_count'))
                .filter(Student.user_id == current_user_id)
                .outerjoin(Loan, and_(Student.id == Loan.student_id, Loan.date_return == None))
                .outerjoin(Book, Loan.book_id == Book.id)
                .outerjoin(last_loan_alias, Student.id == last_loan_alias.student_id)
                .outerjoin(subquery_loan_count, Student.id == subquery_loan_count.c.student_id)
                .group_by(Student.id)
                .order_by(Student.name, Student.firstname)
                .all())

    return students


"""
Get one student by his id with the list of actual loans and the list of old loans
    :param current_user_id: the user id
    :param student_id: the student id
    :return: the student, the list of actual loans, the list of old loans
"""
def get_student_infos(current_user_id, student_id) -> (Student, list, list):
    # Query to get the student
    student = db.session.query(Student).filter(Student.user_id == current_user_id, Student.id == student_id).first()

    # Query to get the current loans
    current_loans = (db.session.query(Loan, Book)
                     .filter(Book.user_id == current_user_id, Loan.student_id == student_id, Loan.date_return == None)
                     .join(Book, Loan.book_id == Book.id)
                     .all())

    # Query to get the past loans
    past_loans = (db.session.query(Loan, Book)
                  .filter(Book.user_id == current_user_id, Loan.student_id == student_id, Loan.date_return != None)
                  .join(Book, Loan.book_id == Book.id)
                  .all())

    return student, current_loans, past_loans


def get_loans(current_user_id) -> list:
    loans = db.session.query(Loan).filter(Loan.user_id == current_user_id).all()
    return loans


def get_book_actual_loan(current_user_id, book_id) -> Loan:
    book_loan = (db.session.query(Loan)
                 .filter(Loan.book_id == book_id, Loan.date_return == None, Book.user_id == current_user_id)
                 .join(Book, Loan.book_id == Book.id)
                 .first())
    return book_loan


def get_book_loans(current_user_id, book_id) -> list:
    book_loans = (db.session.query(Loan)
                  .filter(Loan.book_id == book_id, Book.user_id == current_user_id)
                  .join(Book, Loan.book_id == Book.id)
                  .all())
    return book_loans


def get_book_loan_by_student(current_user_id, book_id) -> Student:
    student = (db.session.query(Student)
                .join(Loan)
                .filter(Student.user_id == current_user_id, Loan.book_id == book_id, Loan.date_return == None)
                .first())
    return student


def get_tags(current_user_id) -> list:
    tags = db.session.query(Tags).filter(Tags.user_id == current_user_id).all()
    return tags


def get_user(current_user_id) -> list:
    user = db.session.query(User.id, User.email, User.name).filter(User.id == current_user_id).first()
    return user


def get_book_tags(current_user_id, book_id) -> list:
    book_tags = (db.session.query(Tags)
                 .join(BookTags)
                 .join(Book)
                 .filter(Book.user_id == current_user_id, Book.id == book_id).all())
    return book_tags


def get_books_most_borrowed(current_user_id, n_books=5) -> list:
    subquery_loan_count = (db.session.query(Loan.book_id, func.count(Loan.id).label('loan_count'))
                           .group_by(Loan.book_id)
                           .subquery())

    books = (db.session.query(Book, func.coalesce(subquery_loan_count.c.loan_count, 0).label('loan_count'))
             .filter(Book.user_id == current_user_id)
             .outerjoin(subquery_loan_count, Book.id == subquery_loan_count.c.book_id)
             .order_by(subquery_loan_count.c.loan_count.desc())
             .limit(n_books).all())

    return books


def get_students_most_borrowed(current_user_id, n_students=5) -> list:
    subquery_loan_count = (db.session.query(Loan.student_id, func.count(Loan.id).label('loan_count'))
                           .group_by(Loan.student_id)
                           .subquery())

    students = (db.session.query(Student, func.coalesce(subquery_loan_count.c.loan_count, 0).label('loan_count'))
                .filter(Student.user_id == current_user_id)
                .outerjoin(subquery_loan_count, Student.id == subquery_loan_count.c.student_id)
                .order_by(subquery_loan_count.c.loan_count.desc())
                .limit(n_students).all())

    return students


def get_last_book_loan(current_user_id, n_books=5) -> list:
    books = (db.session.query(Book, Loan, Student)
             .filter(Book.user_id == current_user_id)
             .outerjoin(Loan, and_(Book.id == Loan.book_id))
             .outerjoin(Student, Loan.student_id == Student.id)
             .order_by(Loan.date_loan.desc())
             .limit(n_books).all())

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
    number_of_day = 365 + int(today.strftime('%w')) - 2

    start_date = today - timedelta(days=number_of_day)
    days = [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(0, number_of_day + 1)]

    # Query to get loans per day
    loans = (db.session.query(func.strftime('%Y-%m-%d', Loan.date_loan).label('year_day'), func.count(Loan.id).label('loan_count'))
             .filter(Book.user_id == current_user_id, Loan.date_loan > func.date('now', f'-{number_of_day} days'))
             .join(Book, Loan.book_id == Book.id)
             .group_by('year_day')
             .all())

    returns = (db.session.query(func.strftime('%Y-%m-%d', Loan.date_return).label('year_day'), func.count(Loan.id).label('return_count'))
                .filter(Book.user_id == current_user_id, Loan.date_return > func.date('now', f'-{number_of_day} days'))
                .join(Book, Loan.book_id == Book.id)
                .group_by('year_day')
                .all())

    combined = {day: {'loan_count': 0, 'return_count': 0} for day in days}

    for loan in loans:
        combined[loan.year_day]['loan_count'] = loan.loan_count

    for r in returns:
        combined[r.year_day]['return_count'] = r.return_count

    result = [(datetime.strptime(day, '%Y-%m-%d'), combined[day]['loan_count'], combined[day]['return_count']) for day in days]

    return result


"""
Get the 5 books that match the search (title, isbn, student name, student firstname)
    :param current_user_id: the user id
    :param search: the search string
    :return: the list of books
"""
def get_search_5_books(current_user_id, search) -> list:
    books = (db.session.query(Book, Loan, Student)
             .filter(Book.user_id == current_user_id,
                     or_(Book.title.ilike('%' + search + '%'), Book.isbn.ilike('%' + search + '%'),
                         Student.name.ilike('%' + search + '%'), Student.firstname.ilike('%' + search + '%')))
             .outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return == None))
             .outerjoin(Student, Loan.student_id == Student.id).limit(5).all())
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
def get_books_sorted(current_user_id, sort='Book.id', sort_order='asc', n_par_page=10, page=1) -> list:
    subquery_tags = (db.session.query(BookTags.book_id, func.group_concat(Tags.name, ',').label('tags'))
                     .join(Tags, BookTags.tag_id == Tags.id)
                     .group_by(BookTags.book_id)
                     .subquery())

    subquery_loan_count = (db.session.query(Loan.book_id, func.count(Loan.id).label('loan_count'))
                           .group_by(Loan.book_id)
                           .subquery())

    books = (db.session.query(Book, Student, subquery_tags.c.tags,
                              func.coalesce(subquery_loan_count.c.loan_count, 0).label('loan_count'))
             .filter(Book.user_id == current_user_id)
             .outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return == None))
             .outerjoin(Student, Loan.student_id == Student.id)
             .outerjoin(subquery_tags, Book.id == subquery_tags.c.book_id)
             .outerjoin(subquery_loan_count, Book.id == subquery_loan_count.c.book_id)
             .order_by(collate(text(sort), 'NOCASE').desc() if sort_order == 'desc' else collate(text(sort), 'NOCASE'))
             .limit(n_par_page).offset((page - 1) * n_par_page))

    return books


def search_books_by_types(current_user_id, search_type, search_value, sort, sort_order, n_books_by_page, page):
    subquery_tags = (db.session.query(BookTags.book_id, func.group_concat(Tags.name, ',').label('tags'))
                     .join(Tags, BookTags.tag_id == Tags.id)
                     .group_by(BookTags.book_id)
                     .subquery())

    subquery_loan_count = (db.session.query(Loan.book_id, func.count(Loan.id).label('loan_count'))
                           .group_by(Loan.book_id)
                           .subquery())

    query = db.session.query(Book, Student, subquery_tags.c.tags, func.coalesce(subquery_loan_count.c.loan_count, 0).label('loan_count'))
    query = query.filter(Book.user_id == current_user_id)
    query = query.outerjoin(Loan, and_(Book.id == Loan.book_id, Loan.date_return == None))
    query = query.outerjoin(Student, Loan.student_id == Student.id)
    query = query.outerjoin(subquery_tags, Book.id == subquery_tags.c.book_id)
    query = query.outerjoin(subquery_loan_count, Book.id == subquery_loan_count.c.book_id)

    if search_type == "titre":
        query = query.filter(Book.title.ilike('%' + search_value + '%'))
    elif search_type == "isbn":
        query = query.filter(Book.isbn.ilike('%' + search_value + '%'))
    elif search_type == "eleve":
        query = query.filter(or_(Student.name.ilike('%' + search_value + '%'), Student.firstname.ilike('%' + search_value + '%')))
    elif search_type == "tags":
        query = query.outerjoin(BookTags, Book.id == BookTags.book_id)
        query = query.outerjoin(Tags, BookTags.tag_id == Tags.id)
        query = query.filter(Tags.name.ilike('%' + search_value + '%'))
    elif search_type == "all":
        query = query.outerjoin(BookTags, Book.id == BookTags.book_id)
        query = query.outerjoin(Tags, BookTags.tag_id == Tags.id)
        query = query.filter(or_(Book.title.ilike('%' + search_value + '%'), Book.isbn.ilike('%' + search_value + '%'),
                                 Student.name.ilike('%' + search_value + '%'), Student.firstname.ilike('%' + search_value + '%'),
                                 Tags.name.ilike('%' + search_value + '%')))

    query = query.order_by(collate(text(sort), 'NOCASE').desc() if sort_order == 'desc' else collate(text(sort), 'NOCASE'))

    n_books = query.count()

    books = query.limit(n_books_by_page).offset((page - 1) * n_books_by_page).all()

    return books, n_books