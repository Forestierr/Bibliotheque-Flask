# Bibliotheque flask

<strong>Ma bibliothèque</strong> est une application web spécialement conçue pour répondre aux
besoins des enseignants dans la gestion de leur bibliothèque de classe. Cette plateforme
intuitive leur permet de centraliser et d’organiser facilement leur collection de livres.
Ils ont la possibilité d’ajouter de nouveaux ouvrages, de modifier les informations existantes
ou de supprimer des livres qui ne sont plus nécessaires. En outre, l'application offre un suivi
détaillé des emprunts effectués par leurs élèves, leur permettant de savoir quels livres ont été
empruntés, par qui et pour combien de temps. Grâce à LivresEnClasse.com, les enseignants peuvent
ainsi encourager la lecture tout en gardant une vue d’ensemble claire et précise sur
l’utilisation des ressources de leur bibliothèque.

## Features

- Add, delete, modify a book
- Add, delete, modify a student
- Scan barcode of a book
- login / logout

## Installation

```bash
pip install requirements.txt
```

Modify the `project\config.py` file to set the secret key.

```python
SECRET_KEY = 'your_new_secret_key'
```

## Utilisation

### Create the database

```bash
flask db init
flask db migrate
flask db upgrade
```

### Update the database

```bash
flask db migrate -m "message"
flask db upgrade
```

### Run the application

```bash
$env:FLASK_APP = "project"
flask run -p 80 -h 0.0.0.0
```

And go to http://127.0.0.1:80

> [!TIP]
> Note: You can use the `--host` and `--port` options to change the host and port of the server.

> [!CAUTION]
> Flask don't run a WSGI server, you should use a production WSGI server like Gunicorn.

## Database

The database is a SQLite database. Stored in `instance\db.sqlite` file.

![Database schema](docs/model.png)

_The **User** is a professor._
