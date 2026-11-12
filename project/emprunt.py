import logging
import math
import time
from datetime import UTC, datetime, timedelta

from flask import (
    Blueprint,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import gettext as _
from flask_login import current_user, login_required

from . import db
from .config_plans import FREE_HISTORY_MONTHS
from .models import Book, Loan, Student
from .query import (
    get_loans_count,
    get_loans_with_infos,
    get_search_5_loans,
    search_loans_by_types,
)

emprunt = Blueprint("emprunt", __name__)
logger = logging.getLogger(__name__)


def get_loan_history_cutoff():
    return datetime.now(UTC).date() - timedelta(days=FREE_HISTORY_MONTHS * 30)


@emprunt.route("/emprunt", methods=["GET", "POST"])
@login_required
def emprunt_db():
    page = 1
    n_books_by_page = 20

    active_loan_filter = (
        request.form.get("active_loan") or request.args.get("active_loan") or "0"
    )

    loans, nb_books = get_loans_with_infos(
        current_user.id,
        active_loan_filter,
        n_books_by_page=n_books_by_page,
        page=page,
    )
    nb_page = math.ceil(nb_books / n_books_by_page) if nb_books else 1
    total_loans = get_loans_count(current_user.id)

    return render_template(
        "emprunt/emprunt.html",
        loans=loans,
        active_loan=active_loan_filter,
        only_active_loans=active_loan_filter in (True, "1", "active"),
        nb_page=nb_page,
        page=page,
        total_loans=total_loans,
        cutoff_date=get_loan_history_cutoff(),
    )


@emprunt.route("/emprunt/<id>", methods=["POST"])
@login_required
def return_loan(id):
    loan = db.session.query(Loan).filter(Loan.id == id).first()
    book = (
        db.session.query(Book).filter(Book.id == loan.book_id).first() if loan else None
    )

    next_url = request.form.get("next") or request.referrer
    if not next_url or (
        not next_url.startswith("/") and not next_url.startswith(request.host_url)
    ):
        next_url = (
            url_for("livre.livre_infos", id=book.id)
            if book
            else url_for("emprunt.emprunt_db")
        )

    # Sécurité anti-boucle : si next_url pointe vers l'URL POST /emprunt/<id>, rediriger vers le livre
    if f"/emprunt/{id}" in next_url:
        next_url = (
            url_for("livre.livre_infos", id=book.id)
            if book
            else url_for("emprunt.emprunt_db")
        )

    if loan:
        if book and book.user_id == current_user.id:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    loan.date_return = datetime.now(tz=UTC).date()
                    db.session.commit()
                    flash(
                        _(
                            "Le livre '%(title)s' a bien été marqué comme retourné.",
                            title=book.title,
                        ),
                        "success",
                    )
                    break
                except Exception as e:  # noqa: BLE001
                    db.session.rollback()
                    if attempt < max_retries - 1 and "locked" in str(e).lower():
                        time.sleep(0.1 * (attempt + 1))
                        loan = db.session.query(Loan).filter(Loan.id == id).first()
                        continue
                    logger.error("Erreur lors du retour de l'emprunt %s : %s", id, e)
                    flash(
                        _("Une erreur est survenue lors du retour du livre."), "error"
                    )
                    break
        else:
            flash(_("Accès non autorisé."), "error")

    # Si HTMX a boosté le formulaire sans cible spécifique, ordonner la redirection navigateur vers next_url
    if request.headers.get("HX-Request") and not request.headers.get("HX-Target"):
        response = make_response("", 200)
        response.headers["HX-Redirect"] = next_url
        return response

    return redirect(next_url)


@emprunt.route("/emprunt/<id>/return-quick", methods=["POST"])
@login_required
def return_loan_quick(id):
    from_url = request.referrer
    if not from_url or not from_url.startswith(request.host_url):
        from_url = url_for("emprunt.emprunt_db")

    loan = db.session.query(Loan).filter(Loan.id == id).first()

    if not loan:
        if request.headers.get("HX-Request"):
            return make_response(
                f"<div class='notification is-danger is-light p-2'>{_('Emprunt introuvable.')}</div>",
                404,
            )
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"error": _("Emprunt introuvable.")}), 404
        flash(_("Emprunt introuvable."), "error")
        return redirect(from_url)

    book = db.session.query(Book).filter(Book.id == loan.book_id).first()
    if not book or book.user_id != current_user.id:
        if request.headers.get("HX-Request"):
            return make_response(
                f"<div class='notification is-danger is-light p-2'>{_('Accès non autorisé.')}</div>",
                403,
            )
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"error": _("Accès non autorisé.")}), 403
        flash(_("Accès non autorisé."), "error")
        return redirect(from_url)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            loan.date_return = datetime.now(tz=UTC).date()
            db.session.commit()
            break
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            if attempt < max_retries - 1 and "locked" in str(e).lower():
                time.sleep(0.1 * (attempt + 1))
                loan = db.session.query(Loan).filter(Loan.id == id).first()
                continue
            logger.error("Erreur lors du retour rapide de l'emprunt %s : %s", id, e)
            if request.headers.get("HX-Request"):
                return make_response(
                    f"<div class='notification is-danger is-light p-2'>{_('Une erreur est survenue lors du retour du livre.')}</div>",
                    500,
                )
            if request.is_json or request.headers.get("Accept") == "application/json":
                return jsonify(
                    {"error": _("Une erreur est survenue lors du retour du livre.")}
                ), 500
            flash(_("Une erreur est survenue lors du retour du livre."), "error")
            return redirect(from_url)

    if request.headers.get("HX-Request"):
        student = (
            db.session.query(Student).filter(Student.id == loan.student_id).first()
        )
        loan_item = type(
            "LoanItem", (), {"Loan": loan, "Book": book, "Student": student}
        )()
        return render_template(
            "emprunt/_loan_row.html",
            loan=loan_item,
            just_returned=True,
            cutoff_date=get_loan_history_cutoff(),
        )

    if request.is_json or request.headers.get("Accept") == "application/json":
        return jsonify(
            {
                "success": True,
                "message": _("Livre retourné avec succès."),
                "book_title": book.title,
                "loan_id": loan.id,
            }
        )

    flash(
        _("Le livre '%(title)s' a bien été marqué comme retourné.", title=book.title),
        "success",
    )
    return redirect(from_url)


@emprunt.route("/emprunt/<id>/delete", methods=["POST"])
@login_required
def delete_loan(id):
    from_url = request.referrer
    if not from_url or not from_url.startswith(request.host_url):
        from_url = url_for("emprunt.emprunt_db")

    loan = db.session.query(Loan).filter(Loan.id == id).first()

    if not loan:
        flash(_("Emprunt introuvable."), "error")
        return redirect(from_url)

    book = db.session.query(Book).filter(Book.id == loan.book_id).first()

    if book.user_id != current_user.id:
        flash(_("Accès non autorisé."), "error")
        return redirect(from_url)

    if loan:
        db.session.delete(loan)
        db.session.commit()

    return redirect(from_url)


@emprunt.route("/emprunt/delete_all", methods=["POST"])
@login_required
def delete_all_loans():
    loans = (
        db.session.query(Loan)
        .join(Book, Loan.book_id == Book.id)
        .filter(Book.user_id == current_user.id)
        .all()
    )

    for loan in loans:
        db.session.delete(loan)

    db.session.commit()

    return redirect(url_for("auth.reglage"))


@emprunt.route("/emprunt/search-preview", methods=["POST"])
@login_required
def search_preview():
    search = request.form.get("search") if request.form.get("search") else ""

    if search == "":
        return make_response("No Content", 204)

    active_loan_filter = request.form.get("active_loan") or "0"

    # Si la recherche est typée (par exemple : titre:Harry Potter)
    search_type = ["titre", "isbn", "eleve", "tags"]
    split = search.split(":", 1)
    if len(split) == 2 and split[0] in search_type:
        search_category = split[0]
        search_value = split[1]
        books, _ = search_loans_by_types(
            current_user.id,
            active_loan_filter,
            search_category,
            search_value,
            "Book.title",
            "asc",
            5,
            1,
        )
    else:
        # Rechercher 5 livres
        books = get_search_5_loans(current_user.id, search)

    return render_template("utils/search_preview.html", books=books)


@emprunt.route("/emprunt/search", methods=["POST"])
@emprunt.route("/emprunt/search/<page>", methods=["POST"])
@login_required
def search(page=1):
    search_type = ["titre", "isbn", "eleve", "tags"]

    search = request.form.get("search") if request.form.get("search") else ""
    sort = request.form.get("sort") if request.form.get("sort") else "pertinent"
    n_books_by_page = (
        request.form.get("n_results") if request.form.get("n_results") else 20
    )
    page = request.form.get("page") if request.form.get("page") else page
    active_loan_filter = request.form.get("active_loan") or "0"
    only_active_loans = active_loan_filter in (True, "1", "active")

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
        case "recent":
            sort = "Loan.date_loan"
            sort_order = "desc"
        case "ancien":
            sort = "Loan.date_loan"
        case _:
            sort = "pertinent"

    n_books = get_loans_count(current_user.id)

    if search == "":
        (loans, n_books) = get_loans_with_infos(
            current_user.id, active_loan_filter, sort, sort_order, n_books_by_page, page
        )
        nb_page = math.ceil(n_books / n_books_by_page)
        return render_template(
            "emprunt/emprunt_list.html",
            loans=loans,
            active_loan=active_loan_filter,
            only_active_loans=only_active_loans,
            nb_page=nb_page,
            page=int(page),
            cutoff_date=get_loan_history_cutoff(),
        )

    # Si la recherche est typée (par exemple : titre:Harry Potter)
    split = search.split(":", 1)

    if len(split) == 2:
        if split[0] in search_type:
            search = split[1]
            (loans, n_books) = search_loans_by_types(
                current_user.id,
                active_loan_filter,
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
            (loans, n_books) = get_loans_with_infos(
                current_user.id,
                active_loan_filter,
                sort,
                sort_order,
                n_books_by_page,
                page,
            )

        nb_page = math.ceil(n_books / n_books_by_page)
        return render_template(
            "emprunt/emprunt_list.html",
            loans=loans,
            active_loan=active_loan_filter,
            only_active_loans=only_active_loans,
            nb_page=nb_page,
            page=int(page),
            cutoff_date=get_loan_history_cutoff(),
        )

    # Recherche par défaut
    (loans, n_books) = search_loans_by_types(
        current_user.id,
        active_loan_filter,
        "all",
        search,
        sort,
        sort_order,
        n_books_by_page,
        page,
    )
    nb_page = math.ceil(n_books / n_books_by_page)

    return render_template(
        "emprunt/emprunt_list.html",
        loans=loans,
        active_loan=active_loan_filter,
        only_active_loans=only_active_loans,
        nb_page=nb_page,
        page=int(page),
        cutoff_date=get_loan_history_cutoff(),
    )
