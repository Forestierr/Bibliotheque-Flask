"""
scripts/generate_pinterest_pins.py

Générateur automatisé de visuels Pinterest haute résolution (1000 x 1500 px, ratio 2:3).
Design épuré, professionnel et minimaliste pour la communauté enseignante :
- Typographie soignée et immédiatement lisible
- Mockup réaliste avec ombre portée douce
- Palette sobre et chaleureuse sans surcharge d'informations ni de couleurs
- Branding discret Livres en Classe
"""

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "project" / "static" / "image" / "pinterest"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

WIDTH = 1000
HEIGHT = 1500

def get_font(size: int, bold: bool = False):
    font_names = (
        ["segoeuib.ttf", "arialbd.ttf", "calibrib.ttf"]
        if bold
        else ["segoeui.ttf", "arial.ttf", "calibri.ttf"]
    )
    for name in font_names:
        path = os.path.join("C:/Windows/Fonts", name)
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

def draw_shadowed_box(base_img, xy, radius=16, fill=(255, 255, 255, 255), shadow_color=(15, 23, 42, 35), shadow_blur=22, offset=(0, 12)):
    """Crée un rectangle avec une ombre portée réaliste et douce."""
    x0, y0, x1, y1 = xy
    shadow_img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_img)
    sx0 = x0 + offset[0]
    sy0 = y0 + offset[1]
    sx1 = x1 + offset[0]
    sy1 = y1 + offset[1]
    s_draw.rounded_rectangle([sx0, sy0, sx1, sy1], radius=radius, fill=shadow_color)
    shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(shadow_blur))
    base_img.paste(shadow_img, (0, 0), shadow_img)

    # Dessine le rectangle principal
    draw = ImageDraw.Draw(base_img)
    draw.rounded_rectangle(xy, radius=radius, fill=fill)
    return draw

def draw_header_badge_and_titles(draw, badge_text, title_line1, title_line2="", subtitle=""):
    """En-tête propre : Badge pilule + Titre principal + Sous-titre."""
    # Badge pilule supérieur
    badge_font = get_font(18, bold=True)
    badge_bbox = badge_font.getbbox(badge_text)
    badge_w = badge_bbox[2] - badge_bbox[0]
    badge_h = badge_bbox[3] - badge_bbox[1]

    bx0 = (WIDTH - badge_w) // 2 - 20
    by0 = 70
    bx1 = bx0 + badge_w + 40
    by1 = by0 + badge_h + 18
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=999, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=2)
    draw.text(((WIDTH - badge_w) // 2, by0 + 8), badge_text, fill=(30, 58, 138, 255), font=badge_font)

    # Titre principal (44px)
    title_font = get_font(44, bold=True)
    if title_line2:
        t1_bbox = title_font.getbbox(title_line1)
        t1_w = t1_bbox[2] - t1_bbox[0]
        draw.text(((WIDTH - t1_w) // 2, 126), title_line1, fill=(15, 23, 42, 255), font=title_font)

        t2_bbox = title_font.getbbox(title_line2)
        t2_w = t2_bbox[2] - t2_bbox[0]
        draw.text(((WIDTH - t2_w) // 2, 180), title_line2, fill=(15, 23, 42, 255), font=title_font)
        sub_y = 244
    else:
        t1_bbox = title_font.getbbox(title_line1)
        t1_w = t1_bbox[2] - t1_bbox[0]
        draw.text(((WIDTH - t1_w) // 2, 140), title_line1, fill=(15, 23, 42, 255), font=title_font)
        sub_y = 205

    # Sous-titre
    if subtitle:
        sub_font = get_font(22, bold=False)
        sub_bbox = sub_font.getbbox(subtitle)
        sub_w = sub_bbox[2] - sub_bbox[0]
        draw.text(((WIDTH - sub_w) // 2, sub_y), subtitle, fill=(71, 85, 105, 255), font=sub_font)

def draw_footer_branding(draw):
    """Pied de page épuré avec adresse du site et repère gratuit."""
    foot_font = get_font(20, bold=True)
    sub_foot_font = get_font(16, bold=False)

    text1 = "livresenclasse.com"
    bbox1 = foot_font.getbbox(text1)
    w1 = bbox1[2] - bbox1[0]
    draw.text(((WIDTH - w1) // 2, 1405), text1, fill=(30, 41, 59, 255), font=foot_font)

    text2 = "Ressource gratuite pour enseignants • Format A4 prêt à imprimer"
    bbox2 = sub_foot_font.getbbox(text2)
    w2 = bbox2[2] - bbox2[0]
    draw.text(((WIDTH - w2) // 2, 1438), text2, fill=(100, 116, 139, 255), font=sub_foot_font)


# =========================================================================
# 1. PASSEPORT DE LECTURE (LIVRET A5)
# =========================================================================
def generate_pin_passeport():
    img = Image.new("RGBA", (WIDTH, HEIGHT), (248, 250, 252, 255))
    draw = ImageDraw.Draw(img)

    draw_header_badge_and_titles(
        draw,
        "LIVRET A5 PLIABLE • ÉCOLE PRIMAIRE",
        "Le Passeport de Lecture",
        "pour vos élèves",
        "Carnet individuel d'autonomie et suivi des lectures de l'année"
    )

    # Mockup : Double volet A5 ouvert (Feuille A4 paysage)
    mockup_box = [80, 310, 920, 1340]
    draw = draw_shadowed_box(img, mockup_box, radius=18, fill=(255, 255, 255, 255))

    # Bordure extérieure élégante de la feuille
    draw.rounded_rectangle(mockup_box, radius=18, outline=(226, 232, 240, 255), width=2)

    # Pliure centrale
    mid_x = (mockup_box[0] + mockup_box[2]) // 2
    for y in range(mockup_box[1] + 25, mockup_box[3] - 25, 12):
        draw.line([(mid_x, y), (mid_x, y + 6)], fill=(203, 213, 225, 255), width=2)

    # --- Volet Gauche : Identité du Lecteur ---
    left_x0, left_y0 = mockup_box[0] + 30, mockup_box[1] + 35
    left_x1, left_y1 = mid_x - 30, mockup_box[3] - 35
    draw.rounded_rectangle([left_x0, left_y0, left_x1, left_y1], radius=10, outline=(37, 99, 235, 255), width=2)

    p_font_sub = get_font(14, bold=True)
    draw.text((left_x0 + 40, left_y0 + 20), "LIVRET INDIVIDUEL DE LECTURE", fill=(30, 58, 138, 255), font=p_font_sub)

    p_font_title = get_font(22, bold=True)
    draw.text((left_x0 + 35, left_y0 + 45), "PASSEPORT DE LECTEUR", fill=(15, 23, 42, 255), font=p_font_title)

    p_font_class = get_font(15, bold=False)
    draw.text((left_x0 + 55, left_y0 + 80), "École élémentaire • Classe de CM1", fill=(100, 116, 139, 255), font=p_font_class)
    draw.line([(left_x0 + 20, left_y0 + 110), (left_x1 - 20, left_y0 + 110)], fill=(37, 99, 235, 255), width=2)

    # Cadre photo autoportrait
    photo_box = [left_x0 + 25, left_y0 + 140, left_x0 + 135, left_y0 + 285]
    draw.rounded_rectangle(photo_box, radius=8, fill=(248, 250, 252, 255), outline=(148, 163, 184, 255), width=2)
    draw.text((left_x0 + 42, left_y0 + 200), "Photo ou\nautoportrait", fill=(148, 163, 184, 255), font=get_font(13, bold=True), align="center")

    # Champs identité
    f_lbl_font = get_font(13, bold=True)
    f_val_font = get_font(15, bold=True)
    champs = [
        ("NOM :", "Dubois", left_y0 + 145),
        ("PRÉNOM :", "Camille", left_y0 + 200),
        ("ANNÉE :", "2026 - 2027", left_y0 + 255),
    ]
    for lbl, val, cy in champs:
        draw.text((left_x0 + 155, cy), lbl, fill=(100, 116, 139, 255), font=f_lbl_font)
        draw.text((left_x0 + 225, cy - 2), val, fill=(15, 23, 42, 255), font=f_val_font)
        draw.line([(left_x0 + 220, cy + 22), (left_x1 - 25, cy + 22)], fill=(203, 213, 225, 255), width=1)

    # Mon objectif de lecture
    draw.text((left_x0 + 25, left_y0 + 325), "MON DÉFI DE L'ANNÉE :", fill=(100, 116, 139, 255), font=f_lbl_font)
    draw.text((left_x0 + 25, left_y0 + 355), "Découvrir au moins 1 livre de chaque genre littéraire !", fill=(30, 58, 138, 255), font=get_font(14, bold=True))

    # Signatures
    draw.line([(left_x0 + 20, left_y1 - 100), (left_x1 - 20, left_y1 - 100)], fill=(226, 232, 240, 255), width=1)
    draw.text((left_x0 + 25, left_y1 - 85), "Signature de l'élève :", fill=(100, 116, 139, 255), font=f_lbl_font)
    draw.line([(left_x0 + 25, left_y1 - 40), (left_x0 + 155, left_y1 - 40)], fill=(148, 163, 184, 255), width=1)

    draw.text((left_x1 - 170, left_y1 - 85), "Signature enseignant(e) :", fill=(100, 116, 139, 255), font=f_lbl_font)
    draw.line([(left_x1 - 170, left_y1 - 40), (left_x1 - 25, left_y1 - 40)], fill=(148, 163, 184, 255), width=1)

    # --- Volet Droit : Suivi des Genres & Lectures ---
    right_x0, right_y0 = mid_x + 30, mockup_box[1] + 35
    right_x1, right_y1 = mockup_box[2] - 30, mockup_box[3] - 35
    draw.rounded_rectangle([right_x0, right_y0, right_x1, right_y1], radius=10, outline=(37, 99, 235, 255), width=2)

    draw.text((right_x0 + 40, right_y0 + 20), "EXPLORATION & DÉCOUVERTES", fill=(30, 58, 138, 255), font=p_font_sub)
    draw.text((right_x0 + 30, right_y0 + 45), "PARCOURS DES GENRES", fill=(15, 23, 42, 255), font=p_font_title)
    draw.text((right_x0 + 40, right_y0 + 80), "Tamponne ou coche chaque genre exploré", fill=(100, 116, 139, 255), font=p_font_class)
    draw.line([(right_x0 + 20, right_y0 + 110), (right_x1 - 20, right_y0 + 110)], fill=(37, 99, 235, 255), width=2)

    # Grille des 8 genres
    genres = [
        ("Roman", "ROM", True), ("Bande Dessinée", "BD", True),
        ("Album", "ALB", True), ("Documentaire", "DOC", False),
        ("Manga", "MNG", True), ("Conte", "CNT", False),
        ("Poésie", "POE", False), ("Presse", "REV", False)
    ]
    gw = (right_x1 - right_x0 - 55) // 2
    gh = 70
    gy0 = right_y0 + 130
    for idx, (g_name, g_code, stamped) in enumerate(genres):
        col = idx % 2
        row = idx // 2
        gx = right_x0 + 25 + col * (gw + 15)
        gy = gy0 + row * (gh + 12)
        draw.rounded_rectangle([gx, gy, gx + gw, gy + gh], radius=8, fill=(248, 250, 252, 255), outline=(203, 213, 225, 255), width=1)
        draw.text((gx + 12, gy + 14), g_name, fill=(15, 23, 42, 255), font=get_font(14, bold=True))
        # Stamp badge
        stamp_box = [gx + gw - 48, gy + 12, gx + gw - 12, gy + 48]
        if stamped:
            draw.rounded_rectangle(stamp_box, radius=6, fill=(239, 246, 255, 255), outline=(37, 99, 235, 255), width=2)
            draw.text((gx + gw - 42, gy + 18), "✓", fill=(37, 99, 235, 255), font=get_font(18, bold=True))
        else:
            draw.rounded_rectangle(stamp_box, radius=6, fill=(255, 255, 255, 255), outline=(203, 213, 225, 255), width=1)
            draw.text((gx + gw - 44, gy + 20), g_code, fill=(148, 163, 184, 255), font=get_font(11, bold=True))

    # Boîte 3 lectures préférées
    top3_box = [right_x0 + 25, right_y1 - 180, right_x1 - 25, right_y1 - 25]
    draw.rounded_rectangle(top3_box, radius=8, fill=(248, 250, 252, 255), outline=(226, 232, 240, 255), width=1)
    draw.text((top3_box[0] + 16, top3_box[1] + 12), "★ Mes 3 lectures coups de cœur :", fill=(15, 23, 42, 255), font=get_font(14, bold=True))
    draw.line([(top3_box[0] + 16, top3_box[1] + 55), (top3_box[2] - 16, top3_box[1] + 55)], fill=(203, 213, 225, 255), width=1)
    draw.text((top3_box[0] + 20, top3_box[1] + 36), "1. Le Petit Prince — Antoine de Saint-Exupéry", fill=(30, 41, 59, 255), font=get_font(13, bold=False))
    draw.line([(top3_box[0] + 16, top3_box[1] + 95), (top3_box[2] - 16, top3_box[1] + 95)], fill=(203, 213, 225, 255), width=1)
    draw.text((top3_box[0] + 20, top3_box[1] + 76), "2. Le Renard de Morlange — Alain Surget", fill=(30, 41, 59, 255), font=get_font(13, bold=False))
    draw.line([(top3_box[0] + 16, top3_box[1] + 135), (top3_box[2] - 16, top3_box[1] + 135)], fill=(203, 213, 225, 255), width=1)

    draw_footer_branding(draw)

    out_file = OUTPUT_DIR / "passeport-de-lecture-a-imprimer.png"
    img.save(out_file, "PNG", optimize=True)
    print(f"Visuel créé : {out_file}")


# =========================================================================
# 2. FICHES COUP DE CŒUR (FANIONS CARTONNÉS)
# =========================================================================
def generate_pin_fiches_avis():
    img = Image.new("RGBA", (WIDTH, HEIGHT), (255, 241, 242, 255))
    draw = ImageDraw.Draw(img)

    draw_header_badge_and_titles(
        draw,
        "RECOMMANDATIONS DE LECTURE ENTRE ÉLÈVES",
        "Fanions « Coup de cœur »",
        "à glisser dans les livres",
        "4 fiches par feuille A4 avec étoiles et avis critique"
    )

    # 2 Fanions réalistes côte à côte
    card_w = 380
    card_h = 960
    card_y = 330

    fanions = [
        (85, "COUP DE CŒUR DE LECTEUR", "Conseillé par : Léa (CM1)", "Le Petit Prince", "Un voyage poétique qui fait réfléchir sur l'amitié."),
        (535, "COUP DE CŒUR DE LECTEUR", "Conseillé par : Thomas (CM1)", "Harry Potter", "L'univers magique et les créatures sont passionnants !")
    ]

    for fx, f_title, f_by, f_book, f_rev in fanions:
        box = [fx, card_y, fx + card_w, card_y + card_h]
        f_draw = draw_shadowed_box(img, box, radius=14, fill=(255, 255, 255, 255), shadow_color=(190, 18, 60, 25))
        f_draw.rounded_rectangle(box, radius=14, outline=(254, 205, 211, 255), width=2)

        # En-tête fanion
        f_draw.text((fx + 30, card_y + 35), f_title, fill=(159, 18, 57, 255), font=get_font(18, bold=True))
        f_draw.text((fx + 55, card_y + 68), "Conseil et partage entre camarades", fill=(100, 116, 139, 255), font=get_font(13, bold=False))
        f_draw.line([(fx + 25, card_y + 98), (fx + card_w - 25, card_y + 98)], fill=(225, 29, 72, 255), width=2)

        # Métadonnées
        f_draw.text((fx + 30, card_y + 125), f_by, fill=(30, 41, 59, 255), font=get_font(15, bold=True))
        f_draw.text((fx + 30, card_y + 165), f"Titre : {f_book}", fill=(30, 41, 59, 255), font=get_font(15, bold=True))

        # Étoiles dorées
        f_draw.text((fx + 30, card_y + 215), "Note :", fill=(100, 116, 139, 255), font=get_font(14, bold=True))
        f_draw.text((fx + 95, card_y + 210), "★ ★ ★ ★ ★", fill=(245, 158, 11, 255), font=get_font(22, bold=True))

        # Texte d'amorce
        f_draw.text((fx + 30, card_y + 270), "Ce qui m'a plu dans cette histoire :", fill=(15, 23, 42, 255), font=get_font(15, bold=True))
        f_draw.text((fx + 30, card_y + 315), f_rev, fill=(71, 85, 105, 255), font=get_font(14, bold=False))

        # Lignes pointillées pour écrire
        for ly in range(card_y + 380, card_y + card_h - 100, 45):
            f_draw.line([(fx + 30, ly), (fx + card_w - 30, ly)], fill=(203, 213, 225, 255), width=1)

        # Pied de fanion
        f_draw.line([(fx + 25, card_y + card_h - 60), (fx + card_w - 25, card_y + card_h - 60)], fill=(241, 245, 249, 255), width=1)
        f_draw.text((fx + 30, card_y + card_h - 45), "À laisser dépasser de la tranche du livre en rayon.", fill=(148, 163, 184, 255), font=get_font(12, bold=False))

    draw_footer_branding(draw)

    out_file = OUTPUT_DIR / "fiche-de-lecture-a-imprimer.png"
    img.save(out_file, "PNG", optimize=True)
    print(f"Visuel créé : {out_file}")


# =========================================================================
# 3. MARQUE-PAGES D'EMPRUNT (RECTO DATE / VERSO ÉTOILES)
# =========================================================================
def generate_pin_marque_pages():
    img = Image.new("RGBA", (WIDTH, HEIGHT), (248, 250, 252, 255))
    draw = ImageDraw.Draw(img)

    draw_header_badge_and_titles(
        draw,
        "SUIVI DES PRÊTS & AVIS LECTEUR",
        "Marque-pages de classe",
        "4 par page A4 prêts à découper",
        "Recto fiche de dates d'emprunt • Verso avis critique et étoiles"
    )

    card_w = 380
    card_h = 960
    card_y = 330

    # Recto (gauche)
    box_r = [85, card_y, 85 + card_w, card_y + card_h]
    draw_r = draw_shadowed_box(img, box_r, radius=14, fill=(255, 255, 255, 255), shadow_color=(37, 99, 235, 25))
    draw_r.rounded_rectangle(box_r, radius=14, outline=(226, 232, 240, 255), width=2)

    draw_r.text((85 + 75, card_y + 35), "FICHE D'EMPRUNT", fill=(30, 58, 138, 255), font=get_font(20, bold=True))
    draw_r.text((85 + 70, card_y + 70), "Bibliothèque de la classe de CM1", fill=(100, 116, 139, 255), font=get_font(14, bold=False))
    draw_r.line([(85 + 25, card_y + 100), (85 + card_w - 25, card_y + 100)], fill=(37, 99, 235, 255), width=2)

    draw_r.text((85 + 30, card_y + 125), "Nom de l'élève :", fill=(71, 85, 105, 255), font=get_font(14, bold=True))
    draw_r.line([(85 + 145, card_y + 142), (85 + card_w - 30, card_y + 142)], fill=(203, 213, 225, 255), width=1)

    # Tableau de dates
    tbl_x0 = 85 + 30
    tbl_x1 = 85 + card_w - 30
    tbl_y0 = card_y + 180
    draw_r.rounded_rectangle([tbl_x0, tbl_y0, tbl_x1, tbl_y0 + 35], radius=6, fill=(241, 245, 249, 255))
    draw_r.text((tbl_x0 + 30, tbl_y0 + 8), "Date prêt", fill=(71, 85, 105, 255), font=get_font(14, bold=True))
    draw_r.text((tbl_x0 + 190, tbl_y0 + 8), "Date retour", fill=(71, 85, 105, 255), font=get_font(14, bold=True))

    for idx, ry in enumerate(range(tbl_y0 + 40, card_y + card_h - 100, 48)):
        draw_r.line([(tbl_x0, ry), (tbl_x1, ry)], fill=(226, 232, 240, 255), width=1)
        if idx == 0:
            draw_r.text((tbl_x0 + 35, ry - 35), "12/09/2026", fill=(30, 41, 59, 255), font=get_font(14, bold=False))
            draw_r.text((tbl_x0 + 195, ry - 35), "26/09/2026", fill=(30, 41, 59, 255), font=get_font(14, bold=False))

    draw_r.line([(tbl_x0 + 160, tbl_y0), (tbl_x0 + 160, card_y + card_h - 100)], fill=(226, 232, 240, 255), width=1)
    draw_r.text((85 + 40, card_y + card_h - 60), "Prends soin de moi et rapporte-moi à l'école !", fill=(148, 163, 184, 255), font=get_font(12, bold=False))

    # Verso (droite)
    box_v = [535, card_y, 535 + card_w, card_y + card_h]
    draw_v = draw_shadowed_box(img, box_v, radius=14, fill=(255, 255, 255, 255), shadow_color=(37, 99, 235, 25))
    draw_v.rounded_rectangle(box_v, radius=14, outline=(226, 232, 240, 255), width=2)

    draw_v.text((535 + 85, card_y + 35), "AVIS DE LECTURE", fill=(30, 58, 138, 255), font=get_font(20, bold=True))
    draw_v.text((535 + 95, card_y + 70), "Partage ton impression", fill=(100, 116, 139, 255), font=get_font(14, bold=False))
    draw_v.line([(535 + 25, card_y + 100), (535 + card_w - 25, card_y + 100)], fill=(37, 99, 235, 255), width=2)

    draw_v.text((535 + 80, card_y + 130), "Note du livre :", fill=(71, 85, 105, 255), font=get_font(14, bold=True))
    draw_v.text((535 + 100, card_y + 160), "★ ★ ★ ★ ★", fill=(245, 158, 11, 255), font=get_font(26, bold=True))

    draw_v.text((535 + 30, card_y + 225), "J'ai aimé ce livre parce que :", fill=(15, 23, 42, 255), font=get_font(15, bold=True))
    draw_v.text((535 + 30, card_y + 265), "Une histoire captivante avec beaucoup\nde suspense et d'humour !", fill=(71, 85, 105, 255), font=get_font(14, bold=False))

    for ly in range(card_y + 350, card_y + card_h - 100, 48):
        draw_v.line([(535 + 30, ly), (535 + card_w - 30, ly)], fill=(203, 213, 225, 255), width=1)

    draw_v.text((535 + 30, card_y + card_h - 60), "Recommandé à mes camarades de classe", fill=(148, 163, 184, 255), font=get_font(12, bold=False))

    draw_footer_branding(draw)

    out_file = OUTPUT_DIR / "marque-pages-a-imprimer.png"
    img.save(out_file, "PNG", optimize=True)
    print(f"Visuel créé : {out_file}")


# =========================================================================
# 4. CHARTE DU COIN LECTURE (AFFICHE A4 / A3)
# =========================================================================
def generate_pin_charte():
    img = Image.new("RGBA", (WIDTH, HEIGHT), (240, 253, 244, 255))
    draw = ImageDraw.Draw(img)

    draw_header_badge_and_titles(
        draw,
        "AFFICHE AVEC CONTRAT DE SIGNATURES",
        "La Charte du Coin Lecture",
        "pour la classe",
        "Les 5 règles d'or pour préserver les livres et la sérénité"
    )

    mockup_box = [130, 310, 870, 1340]
    draw = draw_shadowed_box(img, mockup_box, radius=18, fill=(255, 255, 255, 255), shadow_color=(5, 150, 105, 25))
    draw.rounded_rectangle(mockup_box, radius=18, outline=(187, 247, 208, 255), width=2)

    # Titre affiche
    draw.text((mockup_box[0] + 130, mockup_box[1] + 45), "LA CHARTE DU COIN LECTURE", fill=(20, 83, 45, 255), font=get_font(28, bold=True))
    draw.text((mockup_box[0] + 200, mockup_box[1] + 90), "Les 5 règles d'or de notre classe", fill=(100, 116, 139, 255), font=get_font(18, bold=False))
    draw.line([(mockup_box[0] + 40, mockup_box[1] + 125), (mockup_box[2] - 40, mockup_box[1] + 125)], fill=(5, 150, 105, 255), width=2)

    rules = [
        ("1", "Mains propres & soin", "Je prends soin des livres : je tourne les pages avec délicatesse et des mains propres."),
        ("2", "Silence & respect", "Je lis silencieusement ou je chuchote pour ne pas déranger mes camarades."),
        ("3", "Rangement des bacs", "Je range chaque livre à sa place en respectant son bac et sa couleur de classement."),
        ("4", "Hôpital des livres", "Si un livre est abîmé ou une page détachée, je le signale pour qu'il soit réparé."),
        ("5", "Marque-page", "J'utilise un marque-page pour retrouver ma lecture sans corner les pages.")
    ]

    ry0 = mockup_box[1] + 160
    for num, r_title, r_desc in rules:
        # Numéro cercle
        draw.ellipse([mockup_box[0] + 40, ry0, mockup_box[0] + 86, ry0 + 46], fill=(236, 253, 245, 255), outline=(5, 150, 105, 255), width=2)
        draw.text((mockup_box[0] + 56, ry0 + 9), num, fill=(5, 150, 105, 255), font=get_font(20, bold=True))

        draw.text((mockup_box[0] + 105, ry0 + 2), r_title, fill=(15, 23, 42, 255), font=get_font(18, bold=True))
        draw.text((mockup_box[0] + 105, ry0 + 30), r_desc, fill=(71, 85, 105, 255), font=get_font(14, bold=False))
        ry0 += 115

    # Signatures
    draw.line([(mockup_box[0] + 40, mockup_box[3] - 180), (mockup_box[2] - 40, mockup_box[3] - 180)], fill=(226, 232, 240, 255), width=1)
    draw.text((mockup_box[0] + 45, mockup_box[3] - 155), "Signature des élèves de la classe :", fill=(15, 23, 42, 255), font=get_font(15, bold=True))
    draw.line([(mockup_box[0] + 45, mockup_box[3] - 65), (mockup_box[0] + 380, mockup_box[3] - 65)], fill=(148, 163, 184, 255), width=1)

    draw.text((mockup_box[2] - 250, mockup_box[3] - 155), "Signature de l'enseignant(e) :", fill=(15, 23, 42, 255), font=get_font(15, bold=True))
    draw.line([(mockup_box[2] - 250, mockup_box[3] - 65), (mockup_box[2] - 45, mockup_box[3] - 65)], fill=(148, 163, 184, 255), width=1)

    draw_footer_branding(draw)

    out_file = OUTPUT_DIR / "charte-coin-lecture-a-imprimer.png"
    img.save(out_file, "PNG", optimize=True)
    print(f"Visuel créé : {out_file}")


# =========================================================================
# 5. DIPLÔME DE LECTURE (A4 PAYSAGE)
# =========================================================================
def generate_pin_diplome():
    img = Image.new("RGBA", (WIDTH, HEIGHT), (254, 252, 232, 255))
    draw = ImageDraw.Draw(img)

    draw_header_badge_and_titles(
        draw,
        "VALORISATION & PROGRÈS DE LECTURE",
        "Diplôme de Lecture",
        "prêt à personnaliser",
        "Pour célébrer les paliers de livres lus et rallyes de lecture"
    )

    mockup_box = [80, 380, 920, 1260]
    draw = draw_shadowed_box(img, mockup_box, radius=18, fill=(255, 255, 255, 255), shadow_color=(180, 83, 9, 25))
    draw.rounded_rectangle(mockup_box, radius=18, outline=(254, 240, 138, 255), width=2)

    # Double bordure dorée de diplôme
    inner_box = [mockup_box[0] + 25, mockup_box[1] + 25, mockup_box[2] - 25, mockup_box[3] - 25]
    draw.rounded_rectangle(inner_box, radius=12, outline=(245, 158, 11, 255), width=3)

    # Sceau central doré
    seal_cx = (mockup_box[0] + mockup_box[2]) // 2
    seal_y = mockup_box[1] + 65
    draw.ellipse([seal_cx - 35, seal_y, seal_cx + 35, seal_y + 70], fill=(254, 243, 199, 255), outline=(217, 119, 6, 255), width=2)
    draw.text((seal_cx - 16, seal_y + 18), "★", fill=(217, 119, 6, 255), font=get_font(30, bold=True))

    # Titre et mention
    draw.text((seal_cx - 210, seal_y + 90), "DIPLÔME DE LECTURE", fill=(133, 77, 14, 255), font=get_font(36, bold=True))
    draw.text((seal_cx - 200, seal_y + 145), "Décerné avec toutes les félicitations de la classe à", fill=(100, 116, 139, 255), font=get_font(18, bold=False))

    # Nom de l'élève
    draw.text((seal_cx - 130, seal_y + 200), "Thomas Dubois", fill=(15, 23, 42, 255), font=get_font(38, bold=True))
    draw.line([(seal_cx - 220, seal_y + 255), (seal_cx + 220, seal_y + 255)], fill=(245, 158, 11, 255), width=2)

    # Motif
    draw.text((seal_cx - 300, seal_y + 290), "pour avoir franchi avec brio le palier de 20 livres lus\ndans la bibliothèque de classe !", fill=(71, 85, 105, 255), font=get_font(20, bold=False), align="center")

    # Pied
    draw.text((inner_box[0] + 50, inner_box[3] - 110), "Classe de CM1-B", fill=(15, 23, 42, 255), font=get_font(18, bold=True))
    draw.text((inner_box[0] + 50, inner_box[3] - 75), "Le 18 octobre 2026", fill=(100, 116, 139, 255), font=get_font(16, bold=False))

    draw.text((inner_box[2] - 220, inner_box[3] - 110), "L'enseignant(e) :", fill=(15, 23, 42, 255), font=get_font(18, bold=True))
    draw.line([(inner_box[2] - 220, inner_box[3] - 65), (inner_box[2] - 40, inner_box[3] - 65)], fill=(148, 163, 184, 255), width=1)

    draw_footer_branding(draw)

    out_file = OUTPUT_DIR / "diplome-de-lecture-a-imprimer.png"
    img.save(out_file, "PNG", optimize=True)
    print(f"Visuel créé : {out_file}")


def main():
    print("Génération des visuels Pinterest épurés et professionnels...")
    generate_pin_passeport()
    generate_pin_fiches_avis()
    generate_pin_marque_pages()
    generate_pin_charte()
    generate_pin_diplome()
    print("Tous les visuels Pinterest ont été générés avec succès dans :", OUTPUT_DIR)


if __name__ == "__main__":
    main()
