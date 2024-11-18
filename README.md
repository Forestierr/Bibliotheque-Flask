# Bibliotheque flask

Simple application to manage a library with flask.
Design for professeur and student.

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
