# emprunt.py
import math
from datetime import date

from flask import Blueprint, render_template, redirect, url_for, request, flash, make_response, jsonify
from flask_login import login_required, current_user
from sqlalchemy import and_

from .models import Book, Loan, Student
from . import db
from .query import *

emprunt = Blueprint('emprunt', __name__)

@emprunt.route('/emprunt', methods=['GET', 'POST'])
@login_required
def emprunt_db():
    only_active_loans = True if request.form.get('active_loan') == '1' else False

    loans = get_loans_with_infos(current_user.id, only_active_loans)

    return render_template('emprunt/emprunt.html', loans=loans, only_active_loans=only_active_loans, nb_page=1, page=1)


@emprunt.route('/emprunt/<id>', methods=['GET', 'POST'])
@login_required
def return_loan(id):
    from_url = request.referrer

    loan = db.session.query(Loan).filter(Loan.id == id).first()

    if loan:
        loan.date_return = date.today()
        db.session.commit()


    return redirect(from_url)


@emprunt.route('/emprunt/<id>/delete', methods=['GET', 'POST'])
@login_required
def delete_loan(id):
    loan = db.session.query(Loan).filter(Loan.id == id).first()

    book = db.session.query(Book).filter(Book.id == loan.book_id).first()

    if book.user_id != current_user.id:
        return redirect(url_for('emprunt.emprunt_db'))

    if loan:
        db.session.delete(loan)
        db.session.commit()

    return redirect(url_for('emprunt.emprunt_db'))


@emprunt.route('/emprunt/delete_all', methods=['POST'])
@login_required
def delete_all_loans():
    loans = db.session.query(Loan).join(Book, Loan.book_id == Book.id).filter(Book.user_id == current_user.id).all()

    for loan in loans:
        db.session.delete(loan)

    db.session.commit()

    return redirect(url_for('auth.reglage'))


@emprunt.route('/emprunt/search-preview', methods=['POST'])
@login_required
def search_preview():
    search = request.form.get('search') if request.form.get('search') else ''

    if search == '':
        return make_response('No Content', 204)

    # Si la recherche est typée (par exemple : titre:Harry Potter)
    search_type = ["titre", "isbn", "eleve", "tags"]
    split = search.split(':')
    if len(split) == 2 and split[0] in search_type:
        search = split[1]
        books, _ = search_loans_by_types(current_user.id, split[0], search, 'Book.title', 'asc', 5, 1)
    else:
        # Rechercher 5 livres
        books = get_search_5_loans(current_user.id, search)

    return render_template("utils/search_preview.html", books=books)



@emprunt.route('/emprunt/search', methods=['POST'])
@emprunt.route('/emprunt/search/<page>', methods=['POST'])
@login_required
def search(page=1):
    search_type = ["titre", "isbn", "eleve", "tags"]

    search = request.form.get('search') if request.form.get('search') else ''
    sort = request.form.get('sort') if request.form.get('sort') else 'pertinent'
    n_books_by_page = request.form.get('n_results') if request.form.get('n_results') else 10
    page = request.form.get('page') if request.form.get('page') else page
    print(request.form.get('active_loan'))
    only_active_loans = True if request.form.get('active_loan') == '1' else False

    n_books_by_page = int(n_books_by_page)
    page = int(page)

    # Sort
    sort_order = 'asc'
    match sort:
        case 'pertinent':
            sort = 'Loan.id'
        case 'az':
            sort = 'Book.title'
        case 'za':
            sort = 'Book.title'
            sort_order = 'desc'
        case 'recent':
            sort = 'Loan.date_loan'
            sort_order = 'desc'
        case 'ancien':
            sort = 'Loan.date_loan'
        case _:
            sort = 'Loan.id'

    print(only_active_loans)
    print(search)
    print(sort)

    n_books = get_loans_count(current_user.id)

    if search == '':
        loans = get_loans_with_infos(current_user.id, only_active_loans, sort, sort_order, n_books_by_page, page)
        nb_page = math.ceil(n_books / n_books_by_page)
        return render_template("emprunt/emprunt_list.html", loans=loans, only_active_loans=only_active_loans, nb_page=nb_page, page=int(page))

    # Si la recherche est typée (par exemple : titre:Harry Potter)
    split = search.split(':')

    if len(split) == 2:
        if split[0] in search_type:
            search = split[1]
            (loans, n_books) = search_loans_by_types(current_user.id, only_active_loans, split[0], search, sort, sort_order,
                                                     n_books_by_page, page)
        else:
            flash('Type de recherche inconnu, vous pouvez utiliser : titre:, isbn:, eleve:, tags: suivi de votre recherche.',
                'error')
            # All books
            loans = get_loans_with_infos(current_user.id, only_active_loans, sort, sort_order, n_books_by_page, page)

        nb_page = math.ceil(n_books / n_books_by_page)
        return render_template("emprunt/emprunt_list.html", loans=loans, only_active_loans=only_active_loans, nb_page=nb_page, page=int(page))

    # Recherche par défaut
    (loans, n_books) = search_loans_by_types(current_user.id, only_active_loans, 'all', search, sort, sort_order, n_books_by_page, page)
    nb_page = math.ceil(n_books / n_books_by_page)

    print(loans)

    return render_template("emprunt/emprunt_list.html", loans=loans, only_active_loans=only_active_loans, nb_page=nb_page, page=int(page))