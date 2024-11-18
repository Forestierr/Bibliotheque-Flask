# auth.py
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from .models import User
from . import db

auth = Blueprint('auth', __name__)

@auth.route('/login')
def login():
    return render_template('login.html')

@auth.route('/login', methods=['POST'])
def login_post():
    email = request.form.get('email')
    password = request.form.get('password')
    remember = True if request.form.get('remember') else False

    user = User.query.filter_by(email=email).first()

    # check if user actually exists
    # take the user supplied password, hash it, and compare it to the hashed password in database
    if not user or not check_password_hash(user.password, password):
        flash('Vérifier si votre email et votre mot de passe sont correcte.')
        return redirect(url_for('auth.login')) # if user doesn't exist or password is wrong, reload the page

    # if the above check passes, then we know the user has the right credentials
    login_user(user, remember=remember)
    return redirect(url_for('main.index'))

@auth.route('/signup')
def signup():
    return render_template('signup.html')

@auth.route('/signup', methods=['POST'])
def signup_post():

    email = request.form.get('email')
    name = request.form.get('name')
    password = request.form.get('password')

    user = User.query.filter_by(email=email).first() # if this returns a user, then the email already exists in database

    if user: # if a user is found, we want to redirect back to signup page so user can try again
        flash('Cette email est déjà utilisé.')
        return redirect(url_for('auth.signup'))

    # create new user with the form data. Hash the password so plaintext version isn't saved.
    new_user = User(email=email, name=name, password=generate_password_hash(password, method='pbkdf2:sha256'))

    # add the new user to the database
    db.session.add(new_user)
    db.session.commit()

    return redirect(url_for('auth.login'))

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@auth.route('/contact', methods=['GET', 'POST'])
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

        return redirect(url_for('auth.contact'))

    return render_template('contact.html')

@auth.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    db.session.query(User).filter(User.id == current_user.id).delete()
    db.session.commit()
    logout_user()

    return redirect(url_for('main.index'))

@auth.route('/reglage', methods=['GET', 'POST'])
@login_required
def reglage():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        new_password = request.form.get('new_password')

        user = db.session.query(User).filter(User.id == current_user.id).first()

        if not name:
            flash('Vous devez indiquer votre nom.', 'error')
            return redirect(url_for('auth.reglage'))

        if not email:
            flash('Vous devez indiquer votre email.', 'error')
            return redirect(url_for('auth.reglage'))

        if user.email != email:
            user.email = email

        if user.name != name:
            user.name = name

        if password:
            if not check_password_hash(user.password, password):
                flash('Votre mot de passe est incorrect.', 'error')
                return redirect(url_for('auth.reglage'))
            if not new_password:
                flash('Vous devez indiquer un nouveau mot de passe.', 'error')
                return redirect(url_for('auth.reglage'))
            user.password = generate_password_hash(new_password, method='pbkdf2:sha256')
        else:
            if new_password:
                flash('Vous devez indiquer votre mot de passe actuel.', 'error')
                return redirect(url_for('auth.reglage'))

        db.session.commit()
        flash('Vos informations ont été mises à jour.', 'success')


    user = db.session.query(User).with_entities(User.name, User.email).filter(User.id == current_user.id).first()

    print(user.email)
    print(user.name)

    return render_template('reglage.html', user=user)