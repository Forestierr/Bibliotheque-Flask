# main.py
import os

from flask import Blueprint, render_template, request, url_for, make_response, send_from_directory, app, flash, redirect, current_app, send_file, jsonify
from flask_login import login_required, current_user
from werkzeug.exceptions import HTTPException

from .email import send_email_to_me, send_email_confirmation
from .models import User
from . import db

from .query import *

main = Blueprint('main', __name__)


@main.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    infos = get_app_infos()

    return render_template('index.html', infos=infos)


@main.route('/dashboard')
@login_required
def dashboard():
    n_books = get_books_count(current_user.id)
    n_students = get_students_count(current_user.id)

    # get the 5 books most borrowed
    books = get_books_most_borrowed(current_user.id)

    # get the 5 students who borrowed the most
    students = get_students_most_borrowed(current_user.id)

    # get the 5 list books loaned or returned
    books_loaned = get_last_book_loan(current_user.id)

    # actual month and the 12 previous months
    months = [datetime.now().strftime('%b')]
    for i in range(0, 12):
        months.insert(1, (datetime.now() - timedelta(days=i * 30)).strftime('%b'))

    # get the loan and returns of each day for the last 365 days (max 371 day)
    loans = get_loans_over_the_year(current_user.id)

    # get all months small text version
    # get the index of the monday of the first week of the month
    month_index = 0
    for i in range(0, len(loans), 7):
        # compare the month of the loan with the month of the current date
        if loans[i][0].month == datetime.strptime(months[month_index], '%b').month:
            months[month_index] = (months[month_index], int(i / 7))
            month_index += 1
            if month_index > 12:
                break

    months[-1] = (months[-1], 52)  # last month is always at 52 weeks

    # calc the delta (number of weeks) between each month
    for i in range(0, 12):
        months[i] = (months[i][0], abs(months[i][1] - months[i + 1][1]))
    months[12] = (months[12][0], abs(52 - months[12][1]))

    return render_template('user/dashboard.html', n_books=n_books, n_students=n_students, books=books, students=students, books_loaned=books_loaned, months=months, loans=loans)


@main.route("/sitemap.xml")
@main.route("/sitemap")
def sitemap():
    return render_template('utils/sitemap.xml')


@main.route('/robots.txt')
@main.route('/robot.txt')
@main.route('/robots')
@main.route('/robot')
def robots():
    return render_template('utils/robots.txt')


@main.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(main.root_path, 'static/image'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


@main.route('/contact', methods=['GET', 'POST'])
@login_required
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        firstname = request.form.get('firstname')
        email = request.form.get('email')
        message = request.form.get('message')

        if not name or not firstname or not email or not message:
            flash('Veuillez remplir tous les champs.', 'danger')
            return redirect(url_for('main.contact'))

        # envoi d'un email à l'administrateur
        send_email_to_me('Contact de ' + name + ' ' + firstname, "Email: " + email + "\n" + "Nom: " + name + " " + firstname + "\n\n" + message)

        # envoi d'un email de confirmation à l'utilisateur
        send_email_confirmation(name, firstname, email)

        flash('Votre message a été envoyé avec succès. Vous avez reçu un email de confirmation.', 'success')

        return redirect(url_for('main.contact'))

    user = get_user(current_user.id)

    return render_template('contact.html', user=user)


@main.route('/mentions_legales')
def mentions_legales():
    return render_template('mentions-legales.html')


@main.route('/apropos')
@main.route('/about')
def apropos():
    return render_template('apropos.html')


@main.route('/install')
def install():
    return render_template('utils/app_install.html')


# Error handling
@main.app_errorhandler(HTTPException)
def page_not_found(e):
    return render_template('error.html', error=e), e.code


# PWA code
@main.route('/manifest.json')
def serve_manifest():
    return send_file('manifest.json', mimetype='application/manifest+json')

@main.route('/sw.js')
def serve_sw():
    return send_file('static/javascript/sw.js', mimetype='application/javascript')


@main.route('/api/student_books_read')
@login_required
def api_student_books_read():
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    if not date_from or not date_to:
        return jsonify({'labels': [], 'data': []})
    results = get_books_read_by_students(current_user.id, date_from, date_to)
    labels = [r[0] for r in results]
    data = [r[1] for r in results]
    return jsonify({'labels': labels, 'data': data})

