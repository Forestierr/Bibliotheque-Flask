import os
from flask import render_template
from flask_mail import Message, Mail

from . import mail

def send_email(subject, sender, recipients, text_body):
	msg = Message(subject, sender=sender, recipients=recipients)
	msg.body = text_body
	mail.send(msg)

def send_email_to_me(subject, text_body):
	sender = os.getenv('MAIL_USERNAME')
	recipients = [os.getenv('MAIL_USERNAME')]
	send_email(subject, sender, recipients, text_body)

def send_html_email(subject, sender, recipients, html_body):
	msg = Message(subject, sender=sender, recipients=recipients)
	msg.html = html_body
	mail.send(msg)

def send_email_with_attachment(subject, sender, recipients, text_body, attachment):
	msg = Message(subject, sender=sender, recipients=recipients)
	msg.body = text_body
	msg.attach(attachment)
	mail.send(msg)

def send_email_confirmation(name, firstname, email):
	subject = 'Confirmation de votre message'
	sender = os.getenv('MAIL_USERNAME')
	recipients = [email]
	html_body = render_template('email/email_confirmation.html', name=name, firstname=firstname)
	send_html_email(subject, sender, recipients, html_body)