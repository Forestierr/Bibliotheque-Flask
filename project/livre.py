# livre.py
import logging
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta

import requests
from flask import (
    Blueprint,
    flash,
    has_app_context,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_babel import gettext as _
from flask_login import current_user, login_required

from . import db
from .config_plans import (
    MAX_FREE_BOOKS,
    MAX_FREE_SCANS,
    PRICE_YEARLY_AMOUNT,
)
from .models import Book, BookTags, Loan, Student, Tags
from .query import (
    get_book_actual_loan,
    get_book_by_id,
    get_book_by_title,
    get_book_loan_by_student,
    get_book_tags,
    get_books,
    get_books_by_barcode,
    get_books_by_isbn,
    get_books_count,
    get_books_sorted,
    get_books_student_tags,
    get_loans_with_infos_bookid,
    get_search_5_books,
    get_student_by_id,
    get_students,
    get_tags,
    search_books_by_types,
)

livre = Blueprint("livre", __name__)
logger = logging.getLogger(__name__)


@livre.route("/livre")
@login_required
def livre_db():
    # Valeurs par défaut car la page est appelée sans paramètres
    # Puis on utilise HTMX pour avoir les valeurs des paramètres
    # dans les fonctions search et search_preview
    page = request.args.get("page", 1, type=int)
    n_books_by_page = 20
    search_query = request.args.get("search", "")

    if search_query:
        search_type = ["titre", "isbn", "eleve", "tags"]
        split = search_query.split(":")

        if len(split) == 2 and split[0] in search_type:
            search_val = split[1]
            (books, nb_books) = search_books_by_types(
                current_user.id,
                split[0],
                search_val,
                "pertinent",
                "asc",
                n_books_by_page,
                page,
            )
        else:
            (books, nb_books) = search_books_by_types(
                current_user.id,
                "all",
                search_query,
                "pertinent",
                "asc",
                n_books_by_page,
                page,
            )
    else:
        # get the number of books
        nb_books = (
            db.session.query(Book).filter(Book.user_id == current_user.id).count()
        )
        # Query books and add the student name if the book is loaned
        # (Book, Student, Tags, Loan_count)
        books = get_books_student_tags(current_user.id, n_books_by_page, page)

    # nombre de page
    nb_page = math.ceil(nb_books / n_books_by_page) if nb_books > 0 else 1

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
        search=search_query,
    )


def check_bnf_cover(isbn, timeout=5):
    """Vérifie si la BnF possède une image de couverture pour cet ISBN."""
    if not isbn:
        return False
    url = f"https://openapi.bnf.fr/couverture/image/image/recupererImage?ISBN={isbn}&couverture=1&taille=originale"
    try:
        r = requests.get(url, stream=True, timeout=timeout)
        ct = r.headers.get("Content-Type", "")
        ok = r.status_code == 200 and "image" in ct
        r.close()
        return ok
    except (requests.RequestException, OSError, StopIteration):
        return False


def check_openlibrary_cover(isbn, timeout=5):
    """Vérifie si OpenLibrary possède une couverture pour cet ISBN."""
    if not isbn:
        return False
    url = f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg?default=false"
    try:
        r = requests.get(url, stream=True, timeout=timeout)
        ok = r.status_code == 200
        r.close()
        return ok
    except (requests.RequestException, OSError, StopIteration):
        return False


def resolve_cover_url(isbn, default_img=None):
    """
    Résout la meilleure URL d'image de couverture pour un ISBN :
    1. Image déjà fournie
    2. BnF (Taille originale officielle)
    3. Open Library (Couverture moyenne)
    """
    if default_img:
        return default_img
    if not isbn:
        return None
    clean_isbn = re.sub(r"[^0-9X]", "", str(isbn).upper())
    if not clean_isbn:
        return None
    if check_bnf_cover(clean_isbn):
        return f"https://openapi.bnf.fr/couverture/image/image/recupererImage?ISBN={clean_isbn}&couverture=1&taille=originale"
    if check_openlibrary_cover(clean_isbn):
        return f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-M.jpg"
    return None


def clean_bnf_creator(raw):
    """Nettoie le créateur issu de la notice BnF Dublin Core."""
    if not raw:
        return ""
    s = re.sub(r"\.\s+[A-ZÀ-ÿa-z\s]+$", "", raw.strip())
    s = re.sub(r"\s*\([0-9\.\-\s]+\)", "", s).strip()
    if "," in s:
        parts = [p.strip() for p in s.split(",", 1)]
        if len(parts) == 2 and parts[1]:
            s = f"{parts[1]} {parts[0]}"
    return s.strip()


def get_book_from_bnf(isbn):
    """Interroge l'API SRU de la BnF (Bibliothèque nationale de France)."""
    url = f"https://catalogue.bnf.fr/api/SRU?version=1.2&operation=searchRetrieve&query=bib.isbn+adj+%22{isbn}%22&recordSchema=dublincore"
    headers = {"User-Agent": "Bibliotheque-Flask/1.0"}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        content = getattr(response, "content", None)
        if not isinstance(content, (bytes, bytearray, str)):
            return None
        root = ET.fromstring(content)
        ns = {
            "srw": "http://www.loc.gov/zing/srw/",
            "dc": "http://purl.org/dc/elements/1.1/",
        }
        records = root.findall(".//srw:recordData", ns)
        if not records:
            return None

        rec = records[0]
        raw_title = rec.findtext(".//dc:title", default="", namespaces=ns)
        raw_creator = rec.findtext(".//dc:creator", default="", namespaces=ns)
        raw_publisher = rec.findtext(".//dc:publisher", default="", namespaces=ns)
        raw_date = rec.findtext(".//dc:date", default="", namespaces=ns)
        descriptions = [d.text for d in rec.findall(".//dc:description", ns) if d.text]

        title = raw_title.split(" / ")[0].strip() if raw_title else None
        author = clean_bnf_creator(raw_creator)
        editor = raw_publisher.split("(")[0].strip() if raw_publisher else None
        year_match = re.search(r"\b(19\d\d|20\d\d)\b", raw_date)
        year = year_match.group(1) if year_match else None

        if author and title and title.endswith(author):
            title = title[: -len(author)].strip()
        if title:
            title = re.sub(
                r"\s*\(Nouvelle\s*éd\.?\)", "", title, flags=re.IGNORECASE
            ).strip()

        book_type = None
        for desc in descriptions:
            if "Collection :" in desc:
                book_type = desc.replace("Collection :", "").split(";")[0].strip()
                break

        image_url = None
        if check_bnf_cover(isbn):
            image_url = f"https://openapi.bnf.fr/couverture/image/image/recupererImage?ISBN={isbn}&couverture=1&taille=originale"

        return {
            "title": title,
            "authors": author,
            "author": author,
            "editor": editor,
            "year": year,
            "type": book_type,
            "isbn": isbn,
            "image_url": image_url,
        }
    except (
        requests.RequestException,
        ET.ParseError,
        ValueError,
        IndexError,
        KeyError,
        TypeError,
        StopIteration,
        OSError,
    ) as e:
        logger.warning(
            "Erreur lors de la récupération des données de l'API BnF pour l'ISBN %s : %s",
            isbn,
            e,
        )
    return None


def get_book_from_db(isbn):
    """Vérifie si un livre avec cet ISBN a déjà été enregistré dans la base collaborative."""
    if not isbn or not has_app_context():
        return None
    try:
        book = (
            db.session.query(Book)
            .filter(Book.isbn == isbn, Book.title.isnot(None), Book.title != "")
            .order_by(Book.id.desc())
            .first()
        )
        if book:
            return {
                "title": book.title,
                "authors": book.author,
                "author": book.author,
                "editor": book.editor,
                "year": str(book.year) if book.year else None,
                "type": book.type,
                "isbn": book.isbn,
                "image_url": getattr(book, "image_url", None),
            }
    except (AttributeError, ValueError, OSError) as e:
        logger.debug("Erreur lecture Book cache local : %s", e)
    return None


def get_book_from_google_api(isbn):
    api_key = os.getenv("GOOGLE_BOOK_API_KEY")
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    if api_key:
        url += f"&key={api_key}"

    headers = {"User-Agent": "Bibliotheque-Flask/1.0"}
    max_retries = 1
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code in (503, 429) and attempt < max_retries:
                time.sleep(0.3 * (attempt + 1))
                continue
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("totalItems", 0) > 0:
                items = data.get("items")
                if items and isinstance(items, list) and isinstance(items[0], dict):
                    book = items[0].get("volumeInfo", {})
                    title = book.get("title", None)
                    authors = ", ".join(book.get("authors", []))
                    editor = book.get("publisher", None)
                    raw_year = book.get("publishedDate", None)
                    year = None
                    if raw_year:
                        match = re.search(r"\b(19\d\d|20\d\d)\b", str(raw_year))
                        year = match.group(1) if match else raw_year
                    type = book.get("subtitle", None)

                    image_links = book.get("imageLinks", {})
                    image_url = image_links.get("thumbnail") or image_links.get(
                        "smallThumbnail"
                    )
                    if image_url:
                        image_url = image_url.replace("http://", "https://").replace(
                            "&edge=curl", ""
                        )

                    return {
                        "title": title,
                        "authors": authors,
                        "author": authors,
                        "editor": editor,
                        "year": year,
                        "type": type,
                        "isbn": isbn,
                        "image_url": image_url,
                    }
            break
        except requests.Timeout:
            logger.warning("Timeout lors de la requete Google Books pour ISBN %s", isbn)
            break
        except (requests.RequestException, ValueError) as e:
            if attempt >= max_retries:
                logger.warning(
                    "Erreur lors de la récupération des données de l'API Google Books pour l'ISBN %s : %s",
                    isbn,
                    e,
                )
    return None


def get_book_from_open_library(isbn):
    url = (
        f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    )
    contact_email = os.getenv("CONTACT_EMAIL") or os.getenv("MAIL_USERNAME")
    user_agent = (
        f"Bibliotheque-Flask/1.0 ({contact_email})"
        if contact_email
        else "Bibliotheque-Flask/1.0"
    )
    headers = {"User-Agent": user_agent}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        key = f"ISBN:{isbn}"
        if isinstance(data, dict) and key in data:
            book = data[key]
            title = book.get("title", None)
            authors = ", ".join(
                a.get("name", "")
                for a in book.get("authors", [])
                if isinstance(a, dict) and a.get("name")
            )
            publishers = ", ".join(
                p.get("name", "")
                for p in book.get("publishers", [])
                if isinstance(p, dict) and p.get("name")
            )
            raw_year = book.get("publish_date", None)
            year = None
            if raw_year:
                match = re.search(r"\b(19\d\d|20\d\d)\b", str(raw_year))
                year = match.group(1) if match else raw_year
            type = book.get("subtitle", None)

            cover = book.get("cover", {})
            image_url = cover.get("large") or cover.get("medium") or cover.get("small")
            if image_url:
                image_url = image_url.replace("http://", "https://")

            return {
                "title": title,
                "authors": authors,
                "author": authors,
                "editor": publishers,
                "year": year,
                "type": type,
                "isbn": isbn,
                "image_url": image_url,
            }
    except (requests.RequestException, ValueError) as e:
        logger.warning(
            "Erreur lors de la récupération des données de l'API Open Library pour l'ISBN %s : %s",
            isbn,
            e,
        )
    return None


def get_book_from_api(isbn):
    # Nettoyage de l'ISBN (suppression des tirets et espaces)
    clean_isbn = re.sub(r"[^0-9X]", "", str(isbn).upper()) if isbn else isbn
    if not clean_isbn:
        return None

    # 0. Cache local collaboratif en DB
    cached = get_book_from_db(clean_isbn)
    if cached and cached.get("title"):
        if not cached.get("image_url"):
            cached["image_url"] = resolve_cover_url(clean_isbn)
        return cached

    # 1. Tentative avec Google Books API
    book = get_book_from_google_api(clean_isbn)
    if book and book.get("title"):
        if not book.get("image_url"):
            book["image_url"] = resolve_cover_url(clean_isbn)
        return book

    # 2. Fallback avec Open Library API
    book = get_book_from_open_library(clean_isbn)
    if book and book.get("title"):
        if not book.get("image_url"):
            book["image_url"] = resolve_cover_url(clean_isbn)
        return book

    # 3. Fallback avec BnF (dépôt légal officiel français)
    book = get_book_from_bnf(clean_isbn)
    if book and book.get("title"):
        if not book.get("image_url"):
            book["image_url"] = resolve_cover_url(clean_isbn)
        return book

    return None


@livre.route("/livre/<id>")
@login_required
def livre_infos(id):
    book = get_book_by_id(current_user.id, id)

    if not book:
        flash(_("Le livre que vous souhaitiez voir n'existe pas."), "error")

        return redirect(url_for("livre.livre_db"))

    # get the loans
    actual_loans = get_loans_with_infos_bookid(current_user.id, id, True)

    # get the old loans
    old_loans = get_loans_with_infos_bookid(current_user.id, id, False)

    # Get all students from the current user
    students = get_students(current_user.id)

    # Get the tags of the book
    tags = get_book_tags(current_user.id, id)

    default_days = getattr(current_user, "default_loan_duration_days", None) or 14
    default_expected_date = datetime.now(UTC).date() + timedelta(days=default_days)

    return render_template(
        "livre/livre_info.html",
        book=book,
        actual_loans=actual_loans,
        old_loans=old_loans,
        students=students,
        tags=tags,
        default_expected_date=default_expected_date,
    )


@livre.route("/livre/ajout", methods=["GET", "POST"])
@login_required
def livre_ajout():
    if request.method == "POST":
        # Vérification du quota pour les utilisateurs en plan gratuit
        if not current_user.is_premium:
            current_count = get_books_count(current_user.id)
            if current_count >= MAX_FREE_BOOKS:
                msg = _(
                    "Vous avez atteint la limite de %(max)s livres du plan gratuit. Vos livres existants restent utilisables. Pour en ajouter d'autres, passez Premium ou supprimez un livre existant.",
                    max=MAX_FREE_BOOKS,
                )
                if (
                    request.headers.get("X-Requested-With") == "XMLHttpRequest"
                    or request.is_json
                ):
                    return jsonify({"error": "quota_reached", "message": msg}), 403
                flash(msg, "warning")
                return redirect(url_for("subscription.tarifs"))

        title = request.form.get("title")
        author = request.form.get("author") if request.form.get("author") else None
        editor = request.form.get("editor") if request.form.get("editor") else None
        year = request.form.get("year") if request.form.get("year") else None
        type = request.form.get("type") if request.form.get("type") else None
        isbn = request.form.get("isbn") if request.form.get("isbn") else None
        barcode = (
            request.form.get("barcode").strip()
            if request.form.get("barcode") and request.form.get("barcode").strip()
            else None
        )
        image_url = (
            request.form.get("image_url").strip()
            if request.form.get("image_url") and request.form.get("image_url").strip()
            else None
        )
        if not image_url and isbn:
            clean_isbn = re.sub(r"[^0-9X]", "", str(isbn).upper())
            image_url = resolve_cover_url(clean_isbn)
        tags_hidden = request.form.get("tags") or ""
        tags_raw = request.form.get("tags_input_raw") or ""
        combined_tags_str = f"{tags_hidden},{tags_raw}"
        tags = [t.strip() for t in combined_tags_str.split(",") if t.strip()]
        tags = list(dict.fromkeys(tags))

        if not title:
            flash(_("Veuillez ajouter un titre."), "error")
            return redirect(url_for("livre.livre_ajout"))

        new_book = Book(
            title=title,
            author=author,
            editor=editor,
            year=year,
            type=type,
            isbn=isbn,
            barcode=barcode,
            image_url=image_url,
            user_id=current_user.id,
        )
        db.session.add(new_book)
        db.session.flush()

        # Add the tags to the book
        if tags:
            for tag in tags:
                tag_obj = Tags.query.filter_by(
                    name=tag, user_id=current_user.id
                ).first()
                if not tag_obj:
                    tag_obj = Tags(name=tag, user_id=current_user.id)
                    db.session.add(tag_obj)
                    db.session.flush()
                book_tag = BookTags(book_id=new_book.id, tag_id=tag_obj.id)
                db.session.add(book_tag)

        db.session.commit()

        flash(
            _("Le livre : ") + title + _(" a été ajouté à votre bibliothèque."),
            "success",
        )

        return redirect(url_for("livre.livre_db"))

    # get ISBN and/or barcode from the URL
    isbn = request.args.get("isbn")
    barcode = request.args.get("barcode")

    book = None
    not_found_in_api = False

    if isbn:
        clean_isbn = re.sub(r"[^0-9X]", "", str(isbn).upper()) if isbn else ""
        pending_code = session.pop("pending_scan_code", None)
        is_from_scan = pending_code == clean_isbn or (
            request.args.get("from_scan") == "1" and pending_code is not None
        )

        # Get the book from the API
        book = get_book_from_api(isbn)

        # Si le livre a été trouvé par l'API suite à un scan, on incrémente le compteur
        if book:
            if is_from_scan and not current_user.is_premium:
                current_user.check_and_reset_weekly_scans()
                current_user.free_scans_used = (current_user.free_scans_used or 0) + 1
                db.session.commit()
        else:
            # If the book is not found, we create a book with the ISBN
            # The user can complete the book information (compteur non incrémenté)
            book = {"isbn": isbn}
            not_found_in_api = True
    elif barcode:
        session.pop("pending_scan_code", None)
        book = {"barcode": barcode}

    if book is not None and barcode:
        book["barcode"] = barcode

    # Get all tags (only the name) from the current user
    tags = Tags.query.filter_by(user_id=current_user.id).all()
    tags = [tag.name for tag in tags]

    return render_template(
        "livre/livre_ajout.html",
        tags=tags,
        book=book,
        not_found_in_api=not_found_in_api,
    )


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
    if not current_user.is_premium:
        current_user.check_and_reset_weekly_scans()
    return render_template(
        "livre/livre_scann.html",
        max_scans=MAX_FREE_SCANS,
        price_yearly=int(PRICE_YEARLY_AMOUNT),
    )


@livre.route("/livre/<id>/edit", methods=["GET", "POST"])
@login_required
def livre_edit(id):
    book = get_book_by_id(current_user.id, id)

    if not book:
        flash(_("Le livre que vous souhaitiez éditer n'existe pas."), "error")
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
        barcode = (
            request.form.get("barcode").strip()
            if request.form.get("barcode") and request.form.get("barcode").strip()
            else None
        )
        image_url = (
            request.form.get("image_url").strip()
            if request.form.get("image_url") and request.form.get("image_url").strip()
            else None
        )
        if not image_url and isbn and (isbn != book.isbn or not book.image_url):
            clean_isbn = re.sub(r"[^0-9X]", "", str(isbn).upper())
            image_url = resolve_cover_url(clean_isbn)
        student = request.form.get("student")
        tags = request.form.get("tags")

        if not title:
            flash(_("Veuillez ajouter un titre au livre."), "info")
            return redirect(url_for("livre.livre_edit", id=id))

        # Update the book
        book.title = title
        book.author = author
        book.editor = editor
        book.year = year
        book.type = type
        book.isbn = isbn
        book.barcode = barcode
        if image_url:
            book.image_url = image_url
        elif "image_url" in request.form and not request.form.get("image_url").strip():
            book.image_url = None

        # take the student in the database
        if student:
            student = get_student_by_id(current_user.id, student)

        if student:
            if loan:
                if loan.student_id != student.id:
                    # changement de l'élève
                    # fin de la location
                    loan.date_return = datetime.now(tz=UTC).date()

                    # nouvelle location
                    new_loan = Loan(
                        student_id=student.id,
                        book_id=id,
                        date_loan=datetime.now(tz=UTC).date(),
                    )
                    db.session.add(new_loan)
            else:
                # nouvelle location
                new_loan = Loan(
                    student_id=student.id,
                    book_id=id,
                    date_loan=datetime.now(tz=UTC).date(),
                )
                db.session.add(new_loan)
        else:
            if loan:
                # fin de la location
                loan.date_return = datetime.now(tz=UTC).date()

        # Remove the tags to the book
        book_tags = BookTags.query.filter_by(book_id=id).all()
        for book_tag in book_tags:
            db.session.delete(book_tag)

        tags_hidden = request.form.get("tags") or ""
        tags_raw = request.form.get("tags_input_raw") or ""
        combined_tags_str = f"{tags_hidden},{tags_raw}"
        tags = [t.strip() for t in combined_tags_str.split(",") if t.strip()]
        tags = list(dict.fromkeys(tags))

        # Add the tags to the book
        if tags:
            for tag in tags:
                tag_obj = Tags.query.filter_by(
                    name=tag, user_id=current_user.id
                ).first()
                if not tag_obj:
                    tag_obj = Tags(name=tag, user_id=current_user.id)
                    db.session.add(tag_obj)
                    db.session.flush()
                book_tag = BookTags(book_id=id, tag_id=tag_obj.id)
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
    # Vérification du quota pour les utilisateurs en plan gratuit
    if not current_user.is_premium:
        current_count = get_books_count(current_user.id)
        if current_count >= MAX_FREE_BOOKS:
            msg = _(
                "Vous avez atteint la limite de %(max)s livres du plan gratuit. Vos livres existants restent utilisables. Pour en ajouter d'autres, passez Premium ou supprimez un livre existant.",
                max=MAX_FREE_BOOKS,
            )
            flash(msg, "warning")
            return redirect(url_for("subscription.tarifs"))

    book = get_book_by_id(current_user.id, id)

    if not book:
        flash(_("Le livre que vous souhaitiez dupliquer n'existe pas."), "error")
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

    flash(_("L'exemplaire a été dupliqué avec succès !"), "success")
    return redirect(url_for("livre.livre_infos", id=new_book.id))


@livre.route("/livre/<id>/edit-student", methods=["POST"])
@login_required
def livre_edit_student(id):
    student_id = request.form.get("student_id")

    if not student_id:
        flash(_("Le livre reste dans la bibliothèque."), "info")
        return redirect(url_for("livre.livre_infos", id=id))

    student = get_student_by_id(current_user.id, student_id)

    if not student:
        flash(_("L'élève n'existe pas."), "error")
        return redirect(url_for("livre.livre_infos", id=id))

    date_loan = datetime.now(tz=UTC).date()
    expected_return_date = None
    expected_str = request.form.get("expected_return_date")
    if expected_str:
        try:
            expected_return_date = datetime.strptime(
                expected_str.strip(), "%Y-%m-%d"
            ).date()
        except ValueError:
            expected_return_date = None

    if not expected_return_date:
        duration_days = getattr(current_user, "default_loan_duration_days", 14) or 14
        expected_return_date = date_loan + timedelta(days=duration_days)

    # Create a new loan
    loan = Loan(
        student_id=student.id,
        book_id=id,
        date_loan=date_loan,
        expected_return_date=expected_return_date,
    )
    db.session.add(loan)
    db.session.commit()

    book = get_book_by_id(current_user.id, id)
    student_name = f"{student.firstname} {student.name}".strip()
    flash(
        _(
            "Le livre '%(title)s' a bien été prêté à %(name)s.",
            title=book.title if book else "",
            name=student_name,
        ),
        "success",
    )

    return redirect(url_for("livre.livre_infos", id=id))


@livre.route("/livre/<id>/delete", methods=["POST"])
@login_required
def livre_delete(id):
    book = get_book_by_id(current_user.id, id)

    # Delete the book
    db.session.delete(book)
    db.session.commit()

    flash(_("Le livre a été supprimé."), "info")

    return redirect(url_for("livre.livre_db"))


@livre.route("/livre/<isbn>/exist")
@login_required
def livre_exist(isbn):
    # Vérification du quota de scans pour les comptes gratuits
    if not current_user.is_premium:
        current_user.check_and_reset_weekly_scans()
        if (current_user.free_scans_used or 0) >= MAX_FREE_SCANS:
            return make_response(
                jsonify(
                    {
                        "error": "scan_limit_reached",
                        "message": _(
                            "Vous avez atteint votre quota de %(max)s scans gratuits pour cette semaine ! Vos scans seront réinitialisés dimanche à minuit, ou passez Premium pour scanner en illimité.",
                            max=MAX_FREE_SCANS,
                        ),
                    }
                ),
                403,
            )

    clean_code = str(isbn).strip().replace("-", "")

    # 1. Search by custom barcode first
    books = get_books_by_barcode(current_user.id, isbn)
    if not books:
        # 2. Search by ISBN
        books = get_books_by_isbn(current_user.id, isbn)

    if books:
        # Le livre a été trouvé dans la bibliothèque : on incrémente le compteur de scan
        if not current_user.is_premium:
            current_user.free_scans_used = (current_user.free_scans_used or 0) + 1
            db.session.commit()

        if len(books) == 1:
            book = books[0]
            active_loan = (
                db.session.query(Loan)
                .filter(Loan.book_id == book.id, Loan.date_return.is_(None))
                .first()
            )
            borrower_name = None
            loan_id = None
            if active_loan:
                student = (
                    db.session.query(Student)
                    .filter(Student.id == active_loan.student_id)
                    .first()
                )
                if student:
                    borrower_name = f"{student.firstname} {student.name}".strip()
                loan_id = active_loan.id

            book_title = (
                book.title if isinstance(getattr(book, "title", None), str) else ""
            )

            data = {
                "id": book.id,
                "title": book_title,
                "multiple": False,
                "is_loaned": active_loan is not None,
                "loan_id": loan_id,
                "borrower_name": borrower_name,
            }
        else:
            data = {"ids": [b.id for b in books], "multiple": True}
        return make_response(jsonify(data), 200)

    # Livre non trouvé en base locale : on mémorise le code scanné en session.
    # Le quota de scan ne sera décompté dans /livre/ajout QUE si l'API trouve le livre.
    session["pending_scan_code"] = clean_code

    is_isbn = len(clean_code) == 13 and clean_code.startswith(("978", "979"))
    return make_response(
        jsonify({"error": "Book not found", "is_isbn": is_isbn, "code": isbn}), 404
    )


@livre.route("/livre/delete_all", methods=["POST"])
@login_required
def livre_delete_all():
    books = get_books(current_user.id)

    for book in books:
        clean_isbn = re.sub(r"[^0-9X]", "", str(book.isbn or "")).strip().upper()
        if clean_isbn:
            # Nettoyage des prêts et tags associés à cette copie personnelle
            for loan in list(book.loans):
                db.session.delete(loan)
            for bt in list(book.book_tags):
                db.session.delete(bt)

            # Vérifier si un exemplaire orphelin existe déjà dans la base collective
            orphan_exists = Book.query.filter(
                Book.id != book.id,
                Book.isbn == book.isbn,
                Book.user_id.is_(None),
            ).first()

            if orphan_exists:
                db.session.delete(book)
            else:
                book.user_id = None
                book.barcode = None
        else:
            db.session.delete(book)

    db.session.commit()

    flash(_("Tous les livres ont été supprimés."), "success")

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
            sort = "pertinent"
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
            sort = "pertinent"

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
