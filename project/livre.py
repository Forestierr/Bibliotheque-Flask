from . import db

# livre.py
import math
import os

import requests
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    make_response,
    jsonify,
)
from flask_login import login_required, current_user
from datetime import date

from .models import Book, Loan, BookTags, Tags
from .query import (
    get_book_loan_by_student,
    get_book_actual_loan,
    get_book_by_title,
    get_loans_with_infos_bookid,
    get_tags,
    get_book_by_id,
    get_book_tags,
    get_student_by_id,
    get_books_by_isbn,
    get_books,
    search_books_by_types,
    get_search_5_books,
    get_books_count,
    get_books_sorted,
    get_students,
    get_books_student_tags,
)

livre = Blueprint("livre", __name__)


@livre.route("/livre")
@login_required
def livre_db():
    # Valeurs par défaut car la page est appelée sans paramètres
    # Puis on utilise HTMX pour avoir les valeurs des paramètres
    # dans les fonctions search et search_preview
    page = 1
    n_books_by_page = 20
    # get the number of books
    nb_books = db.session.query(Book).filter(Book.user_id == current_user.id).count()
    # nombre de page
    nb_page = math.ceil(nb_books / n_books_by_page)

    # Query books and add the student name if the book is loaned
    # (Book, Student, Tags, Loan_count)
    books = get_books_student_tags(current_user.id, n_books_by_page, page)

    # When the user types "tags:" or "eleve:" in the search bar, we should display the tags and students
    all_students = get_students(current_user.id)

    tags = get_tags(current_user.id)
    tags = [tag.name for tag in tags]

    return render_template(
        "livre/livre.html",
        books=books,
        students=all_students,
        nb_page=nb_page,
        page=int(page),
        tags=tags,
    )


def get_book_from_api(isbn):
    # get api key from the environnement
    api_key = os.getenv("GOOGLE_BOOK_API_KEY")
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&printType=books&orderBy=relevance&maxResults=1&key={api_key}"
    response = requests.get(url)
    data = response.json()

    if data.get("totalItems", 0) > 0:
        book = data["items"][0]["volumeInfo"]
        title = book.get("title", None)
        authors = ", ".join(book.get("authors", []))
        editor = book.get("publisher", None)
        year = book.get("publishedDate", None)
        type = book.get("subtitle", None)

        return {
            "title": title,
            "authors": authors,
            "editor": editor,
            "year": year,
            "type": type,
            "isbn": isbn,
        }
    else:
        return None


@livre.route("/livre/<id>")
@login_required
def livre_infos(id):
    book = get_book_by_id(current_user.id, id)

    if not book:
        flash("Le livre que vous souhaitiez voir n'existe pas.", "error")

        return redirect(url_for("livre.livre_db"))

    # get the loans
    actual_loans = get_loans_with_infos_bookid(current_user.id, id, True)

    # get the old loans
    old_loans = get_loans_with_infos_bookid(current_user.id, id, False)

    # Get all students from the current user
    students = get_students(current_user.id)

    # Get the tags of the book
    tags = get_book_tags(current_user.id, id)

    return render_template(
        "livre/livre_info.html",
        book=book,
        actual_loans=actual_loans,
        old_loans=old_loans,
        students=students,
        tags=tags,
    )


@livre.route("/livre/ajout", methods=["GET", "POST"])
@login_required
def livre_ajout():
    if request.method == "POST":
        title = request.form.get("title")
        author = request.form.get("author") if request.form.get("author") else None
        editor = request.form.get("editor") if request.form.get("editor") else None
        year = request.form.get("year") if request.form.get("year") else None
        type = request.form.get("type") if request.form.get("type") else None
        isbn = request.form.get("isbn") if request.form.get("isbn") else None
        tags = request.form.get("tags") if request.form.get("tags") else None

        if not title:
            flash("Veuillez ajouter un titre.", "error")
            return redirect(url_for("livre.livre_ajout"))

        tags_in_db = Tags.query.filter_by(user_id=current_user.id).all()
        tags_in_db = [tag.name for tag in tags_in_db]

        # If the tag is not in the database, we add it
        if tags:
            tags = tags.split(",")
            # Remove spaces at the beginning and end of each tag
            tags = [tag.strip() for tag in tags if tag.strip()]
            for tag in tags:
                if tag == "":
                    continue
                if tag not in tags_in_db:
                    new_tag = Tags(name=tag, user_id=current_user.id)
                    db.session.add(new_tag)
                    db.session.commit()

        new_book = Book(
            title=title,
            author=author,
            editor=editor,
            year=year,
            type=type,
            isbn=isbn,
            user_id=current_user.id,
        )
        db.session.add(new_book)

        # Add the tags to the book
        if tags:
            for tag in tags:
                if tag == "":
                    continue
                tag_id = (
                    Tags.query.filter_by(name=tag, user_id=current_user.id).first().id
                )
                book_tag = BookTags(book_id=new_book.id, tag_id=tag_id)
                db.session.add(book_tag)

        db.session.commit()

        flash("Le livre : " + title + " a été ajouté à votre bibliothèque.", "success")

        return redirect(url_for("livre.livre_db"))

    # get ISBN from the URL
    isbn = request.args.get("isbn")

    book = None

    if isbn:
        # Get the book from the API
        book = get_book_from_api(isbn)
        # If the book is not found, we create a book with the ISBN
        # The user can complete the book information
        if not book:
            book = {"isbn": isbn}

    # Get all tags (only the name) from the current user
    tags = Tags.query.filter_by(user_id=current_user.id).all()
    tags = [tag.name for tag in tags]

    return render_template("livre/livre_ajout.html", tags=tags, book=book)


@livre.route("/livre/check-title", methods=["POST"])
@login_required
def check_title():
    title = request.form.get("title")
    if not title:
        return make_response("Titre requis", 400)

    book = get_book_by_title(current_user.id, title)
    if book:
        return make_response(
            "Ce livre existe déjà, un nouvel exemplaire sera ajouté.", 200
        )

    return make_response("", 200)


@livre.route("/livre/scann", methods=["GET", "POST"])
@login_required
def livre_scann():
    return render_template("livre/livre_scann.html")


@livre.route("/livre/<id>/edit", methods=["GET", "POST"])
@login_required
def livre_edit(id):
    book = get_book_by_id(current_user.id, id)

    if not book:
        flash("Le livre que vous souhaitiez éditer n'existe pas.", "error")
        return redirect(url_for("livre.livre_db"))

    # Get all students from the current user
    students = get_students(current_user.id)

    # Get the student who has the book
    loan = get_book_actual_loan(current_user.id, id)
    student = get_book_loan_by_student(current_user.id, id)

    # Get all tags from the current user
    tags = get_tags(current_user.id)
    tags = [tag.name for tag in tags]

    # Get the tags of the book
    book_tags = get_book_tags(current_user.id, id)
    book_tags = [tag.name for tag in book_tags]

    if request.method == "POST":
        title = request.form.get("title")
        author = request.form.get("author")
        editor = request.form.get("editor")
        year = request.form.get("year")
        type = request.form.get("type")
        isbn = request.form.get("isbn")
        student = request.form.get("student")
        tags = request.form.get("tags")

        if not title:
            flash("Veuillez ajouter un titre au livre.", "info")
            return redirect(url_for("livre.livre_edit", id=id))

        # Update the book
        book.title = title
        book.author = author
        book.editor = editor
        book.year = year
        book.type = type
        book.isbn = isbn

        # take the student in the database
        if student:
            student = get_student_by_id(current_user.id, student)

        if student:
            if loan:
                if loan.student_id != student.id:
                    # changement de l'élève
                    # fin de la location
                    loan.date_return = date.today()

                    # nouvelle location
                    new_loan = Loan(
                        student_id=student.id, book_id=id, date_loan=date.today()
                    )
                    db.session.add(new_loan)
            else:
                # nouvelle location
                new_loan = Loan(
                    student_id=student.id, book_id=id, date_loan=date.today()
                )
                db.session.add(new_loan)
        else:
            if loan:
                # fin de la location
                loan.date_return = date.today()

        # Remove the tags to the book
        book_tags = BookTags.query.filter_by(book_id=id).all()
        for book_tag in book_tags:
            db.session.delete(book_tag)

        tags = tags.split(",")

        # Get all tags from the current user
        tags_in_db = Tags.query.filter_by(user_id=current_user.id).all()
        tags_in_db = [tag.name for tag in tags_in_db]

        # If the tag is not in the database, we add it
        for tag in tags:
            if tag == "":
                continue
            if tag not in tags_in_db:
                new_tag = Tags(name=tag, user_id=current_user.id)
                db.session.add(new_tag)
                db.session.commit()

            # Add the tags to the book
            tag_id = Tags.query.filter_by(name=tag, user_id=current_user.id).first().id
            book_tag = BookTags(book_id=id, tag_id=tag_id)
            db.session.add(book_tag)

        db.session.commit()

        return redirect(url_for("livre.livre_db"))

    return render_template(
        "livre/livre_edit.html",
        book=book,
        students=students,
        student=student,
        tags=tags,
        book_tags=book_tags,
    )


@livre.route("/livre/<id>/duplique", methods=["GET"])
@login_required
def livre_duplique(id):
    book = get_book_by_id(current_user.id, id)

    if not book:
        flash("Le livre que vous souhaitiez dupliquer n'existe pas.", "error")
        return redirect(url_for("livre.livre_db"))

    new_title = book.title

    new_book = Book(
        title=new_title,
        author=book.author,
        editor=book.editor,
        year=book.year,
        type=book.type,
        isbn=book.isbn,
        user_id=current_user.id,
    )

    db.session.add(new_book)
    db.session.commit()

    # Add the same tags to the new book
    tags = get_book_tags(current_user.id, id)
    for tag in tags:
        book_tag = BookTags(book_id=new_book.id, tag_id=tag.id)
        db.session.add(book_tag)

    db.session.commit()

    return redirect(url_for("livre.livre_infos", id=new_book.id))


@livre.route("/livre/<id>/edit-student", methods=["POST"])
@login_required
def livre_edit_student(id):
    student_id = request.form.get("student_id")

    if not student_id:
        flash("Le livre reste dans la bibliothèque.", "info")
        return redirect(url_for("livre.livre_infos", id=id))

    student = get_student_by_id(current_user.id, student_id)

    if not student:
        flash("L'élève n'existe pas.", "error")
        return redirect(url_for("livre.livre_infos", id=id))

    # Create a new loan
    loan = Loan(student_id=student.id, book_id=id, date_loan=date.today())
    db.session.add(loan)
    db.session.commit()

    return redirect(url_for("livre.livre_infos", id=id))


@livre.route("/livre/<id>/delete", methods=["POST"])
@login_required
def livre_delete(id):
    book = get_book_by_id(current_user.id, id)

    # Delete the book
    db.session.delete(book)
    db.session.commit()

    flash("Le livre a été supprimé.", "info")

    return redirect(url_for("livre.livre_db"))


@livre.route("/livre/<isbn>/exist")
@login_required
def livre_exist(isbn):
    books = get_books_by_isbn(current_user.id, isbn)

    if books:
        if len(books) == 1:
            data = {"id": books[0].id, "multiple": False}
        else:
            data = {"ids": [b.id for b in books], "multiple": True}
        return make_response(jsonify(data), 200)

    return make_response(jsonify({"error": "Book not found"}), 404)


@livre.route("/livre/delete_all", methods=["POST"])
@login_required
def livre_delete_all():
    books = get_books(current_user.id)

    for book in books:
        db.session.delete(book)

    db.session.commit()

    flash("Tous les livres ont été supprimés.", "success")

    return redirect(url_for("auth.reglage"))


@livre.route("/livre/search-preview", methods=["POST"])
@login_required
def search_preview():
    search = request.form.get("search") if request.form.get("search") else ""

    if search == "":
        return make_response("No Content", 204)

    # Si la recherche est typée (par exemple : titre:Harry Potter)
    search_type = ["titre", "isbn", "eleve", "tags"]
    split = search.split(":")
    if len(split) == 2 and split[0] in search_type:
        search = split[1]
        books, _ = search_books_by_types(
            current_user.id, split[0], search, "Book.title", "asc", 5, 1
        )
    else:
        # Rechercher 5 livres
        books = get_search_5_books(current_user.id, search)

    return render_template("utils/search_preview.html", books=books)


@livre.route("/livre/search", methods=["POST"])
@livre.route("/livre/search/<int:page>", methods=["POST"])
@login_required
def search(page=1):
    search_type = ["titre", "isbn", "eleve", "tags"]

    search = request.form.get("search") if request.form.get("search") else ""
    sort = request.form.get("sort") if request.form.get("sort") else "pertinent"
    n_books_by_page = (
        request.form.get("n_results") if request.form.get("n_results") else 20
    )
    page = request.form.get("page") if request.form.get("page") else page

    n_books_by_page = int(n_books_by_page)
    page = int(page)

    # Sort
    sort_order = "asc"
    match sort:
        case "pertinent":
            sort = "Book.id"
        case "az":
            sort = "Book.title"
        case "za":
            sort = "Book.title"
            sort_order = "desc"
        case "p_emprunte":
            sort = "loan_count"
            sort_order = "desc"
        case "m_emprunte":
            sort = "loan_count"
        case _:
            sort = "Book.id"

    n_books = get_books_count(current_user.id)

    if search == "":
        books = get_books_sorted(
            current_user.id, sort, sort_order, n_books_by_page, page
        )
        nb_page = math.ceil(n_books / n_books_by_page)
        return render_template(
            "livre/livre_list.html", books=books, nb_page=nb_page, page=int(page)
        )

    # Si la recherche est typée (par exemple : titre:Harry Potter)
    split = search.split(":")

    if len(split) == 2:
        if split[0] in search_type:
            search = split[1]
            (books, n_books) = search_books_by_types(
                current_user.id,
                split[0],
                search,
                sort,
                sort_order,
                n_books_by_page,
                page,
            )
        else:
            flash(
                "Type de recherche inconnu, vous pouvez utiliser : titre:, isbn:, eleve:, tags: suivi de votre recherche.",
                "error",
            )
            # All books
            books = get_books_sorted(
                current_user.id, sort, sort_order, n_books_by_page, page
            )

        nb_page = math.ceil(n_books / n_books_by_page)
        return render_template(
            "livre/livre_list.html", books=books, nb_page=nb_page, page=int(page)
        )

    # Recherche par défaut
    (books, n_books) = search_books_by_types(
        current_user.id, "all", search, sort, sort_order, n_books_by_page, page
    )
    nb_page = math.ceil(n_books / n_books_by_page)

    return render_template(
        "livre/livre_list.html", books=books, nb_page=nb_page, page=int(page)
    )
