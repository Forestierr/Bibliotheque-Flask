# main.py

from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from werkzeug.exceptions import HTTPException

main = Blueprint('main', __name__)

@main.route('/')
def index():
    return render_template('index.html')

# Error handling
@main.app_errorhandler(HTTPException)
def page_not_found(e):
    return render_template('error.html', error=e), e.code