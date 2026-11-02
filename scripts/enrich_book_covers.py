#!/usr/bin/env python3
"""
Script d'enrichissement par lots des images de couverture de livres.
Interroge la BnF (Bibliothèque nationale de France) et OpenLibrary
pour associer l'URL de couverture officielle à tous les livres sans image.

Usage :
    python scripts/enrich_book_covers.py [--dry-run] [--limit 50] [--delay 0.1]
"""

import argparse
import os
import re
import sys
import time

# Ajout du dossier racine au PATH Python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from project import create_app, db
from project.livre import check_bnf_cover, check_openlibrary_cover
from project.models import Book


def log(msg, *args):
    now_str = time.strftime("%H:%M:%S")
    formatted = msg % args if args else msg
    print(f"{now_str} [ENRICH] {formatted}", flush=True)


def enrich_books(dry_run=False, limit=None, delay=0.1, batch_commit=25):
    app = create_app()
    with app.app_context():
        total_books = Book.query.count()
        books_without_cover_query = Book.query.filter(
            Book.isbn.isnot(None),
            Book.isbn != "",
            db.or_(Book.image_url.is_(None), Book.image_url == ""),
        )
        total_without_cover = books_without_cover_query.count()

        log("==================================================")
        log("  DÉMARRAGE DE L'ENRICHISSEMENT DES COUVERTURES   ")
        log("==================================================")
        log("Livres au total en base de données : %d", total_books)
        log("Livres sans couverture ayant un ISBN : %d", total_without_cover)

        if total_without_cover == 0:
            log("Tous les livres avec ISBN ont déjà une couverture ! Terminé.")
            return

        # Récupération des ISBN uniques distincts pour économiser les requêtes
        unique_isbns_raw = (
            db.session.query(Book.isbn)
            .filter(
                Book.isbn.isnot(None),
                Book.isbn != "",
                db.or_(Book.image_url.is_(None), Book.image_url == ""),
            )
            .distinct()
            .all()
        )
        unique_isbns = [row[0] for row in unique_isbns_raw if row[0] and row[0].strip()]

        total_unique = len(unique_isbns)
        log(
            "ISBNs uniques distincts à traiter : %d (gain d'optimisation majeur !)",
            total_unique,
        )

        if limit and limit > 0:
            unique_isbns = unique_isbns[:limit]
            log("Limite appliquée : traitement des %d premiers ISBNs", limit)

        if dry_run:
            log("MODE SIMULATION (--dry-run) : aucune modification en base.")

        stats = {
            "processed": 0,
            "bnf_found": 0,
            "openlibrary_found": 0,
            "not_found": 0,
            "books_updated": 0,
            "start_time": time.time(),
        }

        uncommitted_count = 0

        for idx, raw_isbn in enumerate(unique_isbns, start=1):
            clean_isbn = re.sub(r"[^0-9X]", "", str(raw_isbn).upper())

            # Validation élémentaire ISBN (10 ou 13 caractères)
            if len(clean_isbn) not in (10, 13):
                stats["not_found"] += 1
                continue

            cover_url = None
            source = None

            # 1. Vérification BnF (prioritaire, qualité originale officielle)
            if check_bnf_cover(clean_isbn):
                cover_url = f"https://openapi.bnf.fr/couverture/image/image/recupererImage?ISBN={clean_isbn}&couverture=1&taille=originale"
                source = "BnF"
                stats["bnf_found"] += 1
            # 2. Vérification Open Library
            elif check_openlibrary_cover(clean_isbn):
                cover_url = f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-M.jpg"
                source = "OpenLibrary"
                stats["openlibrary_found"] += 1
            else:
                stats["not_found"] += 1

            stats["processed"] += 1

            if cover_url:
                matching_books = Book.query.filter(Book.isbn == raw_isbn).all()
                count_matching = len(matching_books)

                if not dry_run:
                    for b in matching_books:
                        if not b.image_url:
                            b.image_url = cover_url
                    uncommitted_count += count_matching
                    stats["books_updated"] += count_matching
                else:
                    stats["books_updated"] += count_matching

                log(
                    "[%d/%d] %.1f%% | ISBN %s -> %s (%d livre(s) mis à jour)",
                    idx,
                    len(unique_isbns),
                    (idx / len(unique_isbns)) * 100,
                    clean_isbn,
                    source,
                    count_matching,
                )
            else:
                log(
                    "[%d/%d] %.1f%% | ISBN %s -> Aucune couverture publique trouvée",
                    idx,
                    len(unique_isbns),
                    (idx / len(unique_isbns)) * 100,
                    clean_isbn,
                )

            # Commit par lots réguliers
            if not dry_run and uncommitted_count >= batch_commit:
                db.session.commit()
                uncommitted_count = 0

            # Pause polie
            if delay > 0:
                time.sleep(delay)

        # Commit final
        if not dry_run and uncommitted_count > 0:
            db.session.commit()

        elapsed = time.time() - stats["start_time"]
        log("==================================================")
        log("           RÉSUMÉ DE L'ENRICHISSEMENT            ")
        log("==================================================")
        log("Temps écoulé : %.2f secondes", elapsed)
        log("ISBNs traités : %d", stats["processed"])
        log("Couvertures trouvées via BnF : %d", stats["bnf_found"])
        log("Couvertures trouvées via OpenLibrary : %d", stats["openlibrary_found"])
        total_found = stats["bnf_found"] + stats["openlibrary_found"]
        pct = (total_found / max(1, stats["processed"])) * 100
        log("Total couvertures trouvées : %d (%.1f%%)", total_found, pct)
        log("ISBNs sans couverture trouvée : %d", stats["not_found"])
        log(
            "Total fiches livres (Book) mises à jour en DB : %d", stats["books_updated"]
        )
        if dry_run:
            log("RAPPEL : Mode simulation activé, aucune écriture effectuée.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Enrichit les couvertures de livres en base"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simule l'exécution sans écrire en base"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limite le nombre d'ISBNs à traiter"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Délai entre requêtes en secondes (défaut: 0.1)",
    )
    parser.add_argument(
        "--batch-commit",
        type=int,
        default=25,
        help="Nombre de modifications avant chaque commit (défaut: 25)",
    )
    args = parser.parse_args()

    enrich_books(
        dry_run=args.dry_run,
        limit=args.limit,
        delay=args.delay,
        batch_commit=args.batch_commit,
    )
