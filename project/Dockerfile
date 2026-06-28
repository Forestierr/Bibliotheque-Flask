FROM python:3.12

# Installer les dépendances système nécessaires
RUN apt-get update && apt-get install -y \
    locales \
    && locale-gen fr_FR.UTF-8

# Définir la locale par défaut
ENV LANG fr_FR.UTF-8
ENV LANGUAGE fr_FR:fr
ENV LC_ALL fr_FR.UTF-8

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers dans l'image Docker
COPY . /app

# Installer les dépendances Python
RUN pip install --no-cache-dir -r project/requirements.txt

# Exposer le port utilisé par Gunicorn
EXPOSE 5602

# Lancer Gunicorn
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5602", "wsgi:app"]