# main.py
import os

from flask import Blueprint, render_template, request, url_for, make_response, send_from_directory, app, flash, redirect
from flask_flatpages import flatpages
from flask_login import login_required, current_user
from werkzeug.exceptions import HTTPException
import datetime
from urllib.parse import urlparse

main = Blueprint('main', __name__)


@main.route('/')
def index():
    return render_template('index.html')


@main.route("/sitemap.xml")
@main.route("/sitemap")
def sitemap():
    return render_template('sitemap.xml')


@main.route('/robots.txt')
@main.route('/robot.txt')
@main.route('/robots')
@main.route('/robot')
def robots():
    return render_template('robots.txt')


@main.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(main.root_path, 'static/image'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


@main.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        firstname = request.form.get('firstname')
        email = request.form.get('email')
        message = request.form.get('message')
        flash('Votre message a été envoyé avec succès.', 'success')
        flash('Nous vous répondrons dans les plus brefs délais.', 'info')

        # sauvegarde des données dans un fichier (name_firstname_date.txt) dans contact/
        with open("contact/" + name + "_" + firstname + "_" + datetime.now().strftime("%m-%d-%Y_%H-%M-%S") + ".txt", 'w', encoding='utf-8') as f:
            f.write('Date: ' + datetime.now().strftime("%m %B %Y %H:%M:%S") + '\n')
            f.write('Nom: ' + name + '\n')
            f.write('Prénom: ' + firstname + '\n')
            f.write('Email: ' + email + '\n')
            f.write('Message: \n' + message + '\n')

            f.close()

        return redirect(url_for('main.contact'))

    return render_template('contact.html')


@main.route('/mentions_legales')
def mentions_legales():
    return render_template('mentions-legales.html')


@main.route('/apropos')
@main.route('/about')
def apropos():
    return render_template('apropos.html')


# Error handling
@main.app_errorhandler(HTTPException)
def page_not_found(e):
    return render_template('error.html', error=e), e.code