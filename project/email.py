import os
import logging
from threading import Thread
from flask import render_template, current_app
from flask_mail import Message, Mail

from . import mail

def send_email_async(app, msg):
	with app.app_context():
		mail.send(msg)

def send_email(subject, sender, recipients, text_body):
	app = current_app._get_current_object()
	msg = Message(subject, sender=sender, recipients=recipients)
	msg.body = text_body
	thr = Thread(target=send_email_async, args=[app, msg])
	thr.start()
	return thr

def send_email_to_me(subject, text_body):
	sender = os.getenv('MAIL_USERNAME')
	recipients = [os.getenv('MAIL_USERNAME')]
	send_email(subject, sender, recipients, text_body)

def send_html_email(subject, sender, recipients, html_body):
	app = current_app._get_current_object()
	msg = Message(subject, sender=sender, recipients=recipients)
	msg.html = html_body
	thr = Thread(target=send_email_async, args=[app, msg])
	thr.start()
	return thr

def send_email_with_attachment(subject, sender, recipients, text_body, attachment):
	app = current_app._get_current_object()
	msg = Message(subject, sender=sender, recipients=recipients)
	msg.body = text_body
	msg.attach(attachment)
	thr = Thread(target=send_email_async, args=[app, msg])
	thr.start()
	return thr

def send_email_confirmation(name, firstname, email):
	subject = 'Confirmation de votre message'
	sender = os.getenv('MAIL_USERNAME')
	recipients = [email]
	html_body = render_template('email/email_confirmation.html', name=name, firstname=firstname)
	send_html_email(subject, sender, recipients, html_body)

def send_email_bienvenue(name, email):
	subject = 'Bienvenue sur LivresEnClasse'
	sender = os.getenv('MAIL_USERNAME')
	recipients = [email]
	html_body = render_template('email/email_bienvenue.html', name=name)
	send_html_email(subject, sender, recipients, html_body)
