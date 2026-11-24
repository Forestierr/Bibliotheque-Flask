#!/usr/bin/env python3
"""scripts/check_translations.py: Vérificateur automatique des traductions i18n (style Ruff).

Vérifie en une seule commande :
1. Présence des fichiers .po et .mo pour toutes les langues supportées (fr, en, de).
2. Aucune entrée vide (msgstr == "") ni entrée marquée fuzzy (#, fuzzy).
3. Cohérence stricte des variables de formatage (%(var)s, %(n)d, etc.) entre msgid et msgstr.
4. Synchronisation entre le code source (Python + Jinja2 via babel.cfg) et les catalogues .po.
5. Synchronisation réelle entre chaque fichier .po et son binaire compilé .mo.

Usage :
    python scripts/check_translations.py [--skip-extract]
"""

from __future__ import annotations

import argparse
import configparser
import gettext
import pathlib
import re
import sys
from collections import Counter

from babel.messages.extract import extract_from_dir
from babel.messages.pofile import read_po

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
TRANSLATIONS_DIR = ROOT_DIR / "project" / "translations"
BABEL_CFG = ROOT_DIR / "babel.cfg"
LANGUAGES = ("fr", "en", "de")

PLACEHOLDER_RE = re.compile(
    r"%\([^)]+\)[#0\- +]?(?:\d+|\*)?(?:\.\d+)?[diouxXeEfFgGcrsa]"
)


def extract_code_msgids() -> set[str]:
    """Extrait tous les msgid du code source selon babel.cfg."""
    parser = configparser.ConfigParser()
    parser.read(BABEL_CFG, encoding="utf-8")

    method_map = []
    options_map = {}
    for section in parser.sections():
        if section == "extractors":
            continue
        method = section.split(":", 1)[0].strip()
        pattern = section.split(":", 1)[1].strip() if ":" in section else "**"
        method_map.append((pattern, method))
        options_map[pattern] = dict(parser.items(section))

    msgids: set[str] = set()
    for _filename, _lineno, message, _comments, _context in extract_from_dir(
        str(ROOT_DIR),
        method_map=method_map,
        options_map=options_map,
    ):
        if isinstance(message, tuple):
            msgids.update(m for m in message if m)
        elif message:
            msgids.add(message)
    return msgids


def check_translations(*, skip_extract: bool = False) -> list[str]:
    """Retourne la liste des erreurs i18n détectées (vide si tout est conforme)."""
    errors: list[str] = []
    code_msgids = None if skip_extract else extract_code_msgids()

    for lang in LANGUAGES:
        po_path = TRANSLATIONS_DIR / lang / "LC_MESSAGES" / "messages.po"
        mo_path = TRANSLATIONS_DIR / lang / "LC_MESSAGES" / "messages.mo"

        if not po_path.exists():
            errors.append(f"[{lang}] Fichier .po manquant : {po_path}")
            continue
        if not mo_path.exists() or mo_path.stat().st_size == 0:
            errors.append(f"[{lang}] Fichier .mo manquant ou vide : {mo_path}")
            continue

        with po_path.open("rb") as f:
            catalog = read_po(f, locale=lang)

        with mo_path.open("rb") as f:
            mo_trans = gettext.GNUTranslations(f)

        catalog_ids: set[str] = set()
        for msg in catalog:
            if not msg.id:
                continue
            msg_id = msg.id[0] if isinstance(msg.id, tuple) else msg.id
            msg_str = msg.string[0] if isinstance(msg.string, tuple) else msg.string
            catalog_ids.add(msg_id)

            if msg.fuzzy:
                errors.append(f"[{lang}] Entrée fuzzy interdite : {msg_id!r}")
            if not msg_str:
                errors.append(f"[{lang}] Traduction vide : {msg_id!r}")
                continue

            expected_ph = Counter(PLACEHOLDER_RE.findall(msg_id))
            actual_ph = Counter(PLACEHOLDER_RE.findall(msg_str))
            if expected_ph != actual_ph:
                errors.append(
                    f"[{lang}] Variables incohérentes pour {msg_id!r} : "
                    f"attendu {dict(expected_ph)}, trouvé {dict(actual_ph)}"
                )

            compiled = mo_trans.gettext(msg_id)
            if compiled != msg_str:
                errors.append(
                    f"[{lang}] Fichier .mo désynchronisé pour {msg_id!r} "
                    "(exécutez 'pybabel compile -d project/translations')"
                )

        if code_msgids is not None:
            missing_in_po = sorted(code_msgids - catalog_ids)
            for m in missing_in_po:
                errors.append(
                    f"[{lang}] Chaîne extraite du code absente du .po : {m!r} "
                    "(exécutez pybabel extract/update)"
                )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vérifie la complétude et la compilation des traductions i18n."
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Ignore l'extraction des sources pour une vérification ultra-rapide des .po/.mo.",
    )
    args = parser.parse_args()

    errors = check_translations(skip_extract=args.skip_extract)
    if errors:
        print(f"Echec i18n : {len(errors)} problème(s) détecté(s) :", file=sys.stderr)
        for err in errors[:50]:
            print(f"  - {err}", file=sys.stderr)
        if len(errors) > 50:
            print(f"  ... et {len(errors) - 50} autres.", file=sys.stderr)
        return 1

    print("All translation checks passed! (0 empty, 0 fuzzy, .mo and sources synced)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
