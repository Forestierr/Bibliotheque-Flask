"""
Script de génération des visuels verticaux optimisés pour Pinterest (1000 x 1500 px, ratio 2:3).
Produit des graphiques professionnels haute résolution avec textes lisibles en overlay,
mockups réalistes de feuilles A4, badges d'accroche et branding Livres en Classe.
"""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent
    / "project"
    / "static"
    / "image"
    / "pinterest"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_font(size, bold=False):
    font_paths = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:  # noqa: BLE001, S112
                continue
    return ImageFont.load_default()


def draw_rounded_rect_with_shadow(
    draw,
    img,
    xy,
    radius,
    fill,
    shadow_color=(0, 0, 0, 35),
    shadow_offset=(0, 10),
    shadow_blur=15,
):
    """Dessine un rectangle arrondi avec ombre portée douce."""
    x0, y0, x1, y1 = xy
    shadow_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_img)
    sx0 = x0 + shadow_offset[0]
    sy0 = y0 + shadow_offset[1]
    sx1 = x1 + shadow_offset[0]
    sy1 = y1 + shadow_offset[1]
    s_draw.rounded_rectangle([sx0, sy0, sx1, sy1], radius=radius, fill=shadow_color)
    shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(shadow_blur))
    img.paste(shadow_img, (0, 0), shadow_img)
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def create_pin_marque_pages():
    width, height = 1000, 1500
    img = Image.new("RGBA", (width, height), (248, 250, 252, 255))
    draw = ImageDraw.Draw(img)

    # Bande décorative supérieure
    draw.rectangle([0, 0, width, 24], fill=(30, 64, 175, 255))

    # 1. Badge supérieur
    badge_font = get_font(26, bold=True)
    badge_text = "À IMPRIMER GRATUITEMENT • FORMAT A4"
    badge_w = draw.textlength(badge_text, font=badge_font)
    badge_x = (width - badge_w) // 2
    draw.rounded_rectangle(
        [badge_x - 24, 50, badge_x + badge_w + 24, 100],
        radius=25,
        fill=(238, 242, 255, 255),
        outline=(199, 210, 254, 255),
        width=2,
    )
    draw.text((badge_x, 62), badge_text, fill=(55, 48, 163, 255), font=badge_font)

    # 2. Titre principal en overlay
    title1_font = get_font(60, bold=True)
    title2_font = get_font(52, bold=True)
    sub_font = get_font(30, bold=False)

    t1 = "MARQUE-PAGES DE LECTURE"
    t1_w = draw.textlength(t1, font=title1_font)
    draw.text(((width - t1_w) // 2, 125), t1, fill=(15, 23, 42, 255), font=title1_font)

    t2 = "Suivi d'Emprunt & Fiche d'Avis"
    t2_w = draw.textlength(t2, font=title2_font)
    draw.text(((width - t2_w) // 2, 200), t2, fill=(29, 78, 216, 255), font=title2_font)

    sub = "Pour la bibliothèque de classe, la BCD et le rallye lecture"
    sub_w = draw.textlength(sub, font=sub_font)
    draw.text(
        ((width - sub_w) // 2, 270), sub, fill=(100, 116, 139, 255), font=sub_font
    )

    # 3. Mockup visuel central : 3 marque-pages réalistes côte à côte
    mockup_y0 = 340
    mockup_y1 = 1040
    card_w = 230
    gap = 40
    start_x = (width - (3 * card_w + 2 * gap)) // 2

    card_styles = [
        {
            "bg": (255, 255, 255, 255),
            "accent": (37, 99, 235, 255),
            "title": "FICHE D'EMPRUNT",
            "stars": False,
        },
        {
            "bg": (255, 255, 255, 255),
            "accent": (16, 185, 129, 255),
            "title": "AVIS DE LECTURE",
            "stars": True,
        },
        {
            "bg": (255, 255, 255, 255),
            "accent": (245, 158, 11, 255),
            "title": "FICHE D'EMPRUNT",
            "stars": False,
        },
    ]

    for idx, c in enumerate(card_styles):
        cx0 = start_x + idx * (card_w + gap)
        cx1 = cx0 + card_w

        draw_rounded_rect_with_shadow(
            draw, img, [cx0, mockup_y0, cx1, mockup_y1], radius=16, fill=c["bg"]
        )
        draw.rounded_rectangle(
            [cx0, mockup_y0, cx1, mockup_y1],
            radius=16,
            outline=(226, 232, 240, 255),
            width=2,
        )

        # En-tête du marque-page
        draw.rounded_rectangle(
            [cx0 + 15, mockup_y0 + 16, cx1 - 15, mockup_y0 + 64],
            radius=8,
            fill=c["accent"],
        )
        card_t_font = get_font(18, bold=True)
        ct_w = draw.textlength(c["title"], font=card_t_font)
        draw.text(
            (cx0 + (card_w - ct_w) // 2, mockup_y0 + 29),
            c["title"],
            fill=(255, 255, 255, 255),
            font=card_t_font,
        )

        # Lignes simulées dans la carte
        sub_card_font = get_font(14, bold=True)
        draw.text(
            (cx0 + 20, mockup_y0 + 80),
            "Classe de CM1-B",
            fill=(71, 85, 105, 255),
            font=sub_card_font,
        )

        draw.text(
            (cx0 + 20, mockup_y0 + 115),
            "Emprunteur :",
            fill=(100, 116, 139, 255),
            font=get_font(13, bold=True),
        )
        draw.line(
            [cx0 + 20, mockup_y0 + 145, cx1 - 20, mockup_y0 + 145],
            fill=(203, 213, 225, 255),
            width=2,
        )

        if c["stars"]:
            stars_font = get_font(28, bold=True)
            draw.text(
                (cx0 + 20, mockup_y0 + 175),
                "Mon avis :",
                fill=(100, 116, 139, 255),
                font=get_font(13, bold=True),
            )
            draw.text(
                (cx0 + 25, mockup_y0 + 205),
                "★ ★ ★ ★ ★",
                fill=c["accent"],
                font=stars_font,
            )

            draw.text(
                (cx0 + 20, mockup_y0 + 260),
                "Ce que j'ai aime :",
                fill=(100, 116, 139, 255),
                font=get_font(13, bold=True),
            )
            for line_idx in range(6):
                ly = mockup_y0 + 300 + line_idx * 45
                draw.line(
                    [cx0 + 20, ly, cx1 - 20, ly], fill=(226, 232, 240, 255), width=2
                )
        else:
            table_y = mockup_y0 + 175
            draw.text(
                (cx0 + 20, table_y),
                "Dates de pret :",
                fill=(100, 116, 139, 255),
                font=get_font(13, bold=True),
            )

            draw.rectangle(
                [cx0 + 20, table_y + 25, cx1 - 20, table_y + 55],
                fill=(241, 245, 249, 255),
            )
            draw.text(
                (cx0 + 30, table_y + 32),
                "Pret",
                fill=(71, 85, 105, 255),
                font=get_font(12, bold=True),
            )
            draw.text(
                (cx0 + 120, table_y + 32),
                "Retour",
                fill=(71, 85, 105, 255),
                font=get_font(12, bold=True),
            )

            for r_idx in range(7):
                ry = table_y + 55 + r_idx * 45
                draw.line(
                    [cx0 + 20, ry, cx1 - 20, ry], fill=(226, 232, 240, 255), width=2
                )
                draw.line(
                    [cx0 + 110, table_y + 25, cx0 + 110, ry],
                    fill=(226, 232, 240, 255),
                    width=1,
                )

        draw.text(
            (cx0 + 25, mockup_y1 - 40),
            "Prends soin de moi !",
            fill=(148, 163, 184, 255),
            font=get_font(12, bold=False),
        )

    # 4. Puces d'arguments
    bullet_box_y = 1080
    bullets = [
        "✔ 4 marque-pages par page A4 (Pliable ou Recto/Verso)",
        "✔ Suivi rigoureux des dates & avis critique des eleves",
        "✔ Pret a massicoter • 100% personnalisable en ligne",
    ]
    b_font = get_font(23, bold=True)
    for b_idx, b_text in enumerate(bullets):
        draw.text(
            (120, bullet_box_y + b_idx * 46),
            b_text,
            fill=(30, 41, 59, 255),
            font=b_font,
        )

    # 5. Call to action
    cta_y = 1250
    cta_w = 680
    cta_h = 90
    cta_x = (width - cta_w) // 2
    draw_rounded_rect_with_shadow(
        draw,
        img,
        [cta_x, cta_y, cta_x + cta_w, cta_y + cta_h],
        radius=45,
        fill=(225, 29, 72, 255),
        shadow_color=(225, 29, 72, 60),
    )

    cta_font = get_font(32, bold=True)
    cta_text = "📌 Epingler & Imprimer en PDF"
    ct_text_w = draw.textlength(cta_text, font=cta_font)
    draw.text(
        (cta_x + (cta_w - ct_text_w) // 2, cta_y + 26),
        cta_text,
        fill=(255, 255, 255, 255),
        font=cta_font,
    )

    # 6. Footer
    footer_font = get_font(22, bold=True)
    f_text = (
        "LIVRESENCLASSE.COM  •  L'outil de gestion de bibliotheque pour enseignants"
    )
    f_w = draw.textlength(f_text, font=footer_font)
    draw.text(
        ((width - f_w) // 2, 1390), f_text, fill=(100, 116, 139, 255), font=footer_font
    )

    output_path = OUTPUT_DIR / "marque-pages-a-imprimer.png"
    img.convert("RGB").save(output_path, "PNG", quality=95)
    print(f"Genere : {output_path}")


def create_pin_diplome():
    width, height = 1000, 1500
    img = Image.new("RGBA", (width, height), (254, 252, 246, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width, 24], fill=(180, 83, 9, 255))

    badge_font = get_font(26, bold=True)
    badge_text = "À IMPRIMER GRATUITEMENT • FORMAT A4 PAYSAGE"
    badge_w = draw.textlength(badge_text, font=badge_font)
    badge_x = (width - badge_w) // 2
    draw.rounded_rectangle(
        [badge_x - 24, 50, badge_x + badge_w + 24, 100],
        radius=25,
        fill=(254, 243, 199, 255),
        outline=(252, 211, 77, 255),
        width=2,
    )
    draw.text((badge_x, 62), badge_text, fill=(180, 83, 9, 255), font=badge_font)

    title1_font = get_font(58, bold=True)
    title2_font = get_font(50, bold=True)
    sub_font = get_font(30, bold=False)

    t1 = "DIPLÔME DE LECTURE"
    t1_w = draw.textlength(t1, font=title1_font)
    draw.text(((width - t1_w) // 2, 125), t1, fill=(15, 23, 42, 255), font=title1_font)

    t2 = "Champion & Défi de Lecture"
    t2_w = draw.textlength(t2, font=title2_font)
    draw.text(((width - t2_w) // 2, 200), t2, fill=(217, 119, 6, 255), font=title2_font)

    sub = "Pour valoriser les progres et celebrer les livres lus (CP a CM2)"
    sub_w = draw.textlength(sub, font=sub_font)
    draw.text(
        ((width - sub_w) // 2, 270), sub, fill=(100, 116, 139, 255), font=sub_font
    )

    # Mockup
    mockup_x0 = 90
    mockup_x1 = 910
    mockup_y0 = 360
    mockup_y1 = 980

    draw_rounded_rect_with_shadow(
        draw,
        img,
        [mockup_x0, mockup_y0, mockup_x1, mockup_y1],
        radius=20,
        fill=(255, 255, 255, 255),
    )
    draw.rounded_rectangle(
        [mockup_x0, mockup_y0, mockup_x1, mockup_y1],
        radius=20,
        outline=(251, 191, 36, 255),
        width=3,
    )
    draw.rounded_rectangle(
        [mockup_x0 + 20, mockup_y0 + 20, mockup_x1 - 20, mockup_y1 - 20],
        radius=14,
        outline=(217, 119, 6, 255),
        width=2,
    )

    badge_circle_x = (mockup_x0 + mockup_x1) // 2
    badge_circle_y = mockup_y0 + 90
    draw.ellipse(
        [
            badge_circle_x - 45,
            badge_circle_y - 45,
            badge_circle_x + 45,
            badge_circle_y + 45,
        ],
        fill=(254, 243, 199, 255),
        outline=(245, 158, 11, 255),
        width=3,
    )

    # Médaille étoile
    draw.text(
        (badge_circle_x - 22, badge_circle_y - 25),
        "★",
        font=get_font(42, bold=True),
        fill=(217, 119, 6, 255),
    )

    dip_t = "DIPLÔME DE LECTURE"
    dip_tf = get_font(38, bold=True)
    dt_w = draw.textlength(dip_t, font=dip_tf)
    draw.text(
        ((width - dt_w) // 2, mockup_y0 + 160),
        dip_t,
        fill=(180, 83, 9, 255),
        font=dip_tf,
    )

    dip_c = "DÉCERNÉ AVEC TOUTES LES FÉLICITATIONS À :"
    dip_cf = get_font(18, bold=True)
    dc_w = draw.textlength(dip_c, font=dip_cf)
    draw.text(
        ((width - dc_w) // 2, mockup_y0 + 220),
        dip_c,
        fill=(100, 116, 139, 255),
        font=dip_cf,
    )

    student_name = "Léa Martin"
    sn_font = get_font(46, bold=True)
    sn_w = draw.textlength(student_name, font=sn_font)
    draw.text(
        ((width - sn_w) // 2, mockup_y0 + 265),
        student_name,
        fill=(15, 23, 42, 255),
        font=sn_font,
    )
    draw.line(
        [(width - 400) // 2, mockup_y0 + 330, (width + 400) // 2, mockup_y0 + 330],
        fill=(217, 119, 6, 255),
        width=2,
    )

    felic_t = "Pour avoir franchi avec passion le cap des 10 livres lus !"
    felic_f = get_font(22, bold=False)
    ft_w = draw.textlength(felic_t, font=felic_f)
    draw.text(
        ((width - ft_w) // 2, mockup_y0 + 360),
        felic_t,
        fill=(71, 85, 105, 255),
        font=felic_f,
    )

    draw.line(
        [mockup_x0 + 80, mockup_y1 - 90, mockup_x0 + 320, mockup_y1 - 90],
        fill=(203, 213, 225, 255),
        width=2,
    )
    draw.text(
        (mockup_x0 + 120, mockup_y1 - 80),
        "L'enseignant(e)",
        fill=(100, 116, 139, 255),
        font=get_font(18, bold=True),
    )

    draw.line(
        [mockup_x1 - 320, mockup_y1 - 90, mockup_x1 - 80, mockup_y1 - 90],
        fill=(203, 213, 225, 255),
        width=2,
    )
    draw.text(
        (mockup_x1 - 270, mockup_y1 - 80),
        "Le Directeur / La Directrice",
        fill=(100, 116, 139, 255),
        font=get_font(18, bold=True),
    )

    bullet_box_y = 1040
    bullets = [
        "✔ Paliers ajustables : 5, 10, 20 livres ou rallye de lecture",
        "✔ 6 themes visuels (Or prestige, bleu ecolier, vert, coloriage N&B)",
        "✔ Remplissage individuel ou generation pour toute la classe en 1 clic",
    ]
    b_font = get_font(23, bold=True)
    for b_idx, b_text in enumerate(bullets):
        draw.text(
            (95, bullet_box_y + b_idx * 48), b_text, fill=(30, 41, 59, 255), font=b_font
        )

    cta_y = 1250
    cta_w = 680
    cta_h = 90
    cta_x = (width - cta_w) // 2
    draw_rounded_rect_with_shadow(
        draw,
        img,
        [cta_x, cta_y, cta_x + cta_w, cta_y + cta_h],
        radius=45,
        fill=(225, 29, 72, 255),
        shadow_color=(225, 29, 72, 60),
    )

    cta_font = get_font(32, bold=True)
    cta_text = "📌 Epingler & Generer les Diplomes"
    ct_text_w = draw.textlength(cta_text, font=cta_font)
    draw.text(
        (cta_x + (cta_w - ct_text_w) // 2, cta_y + 26),
        cta_text,
        fill=(255, 255, 255, 255),
        font=cta_font,
    )

    footer_font = get_font(22, bold=True)
    f_text = (
        "LIVRESENCLASSE.COM  •  L'outil de gestion de bibliotheque pour enseignants"
    )
    f_w = draw.textlength(f_text, font=footer_font)
    draw.text(
        ((width - f_w) // 2, 1390), f_text, fill=(100, 116, 139, 255), font=footer_font
    )

    output_path = OUTPUT_DIR / "diplome-de-lecture-a-imprimer.png"
    img.convert("RGB").save(output_path, "PNG", quality=95)
    print(f"Genere : {output_path}")


def create_pin_fiches_avis():
    width, height = 1000, 1500
    img = Image.new("RGBA", (width, height), (255, 241, 242, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width, 24], fill=(225, 29, 72, 255))

    badge_font = get_font(26, bold=True)
    badge_text = "À IMPRIMER GRATUITEMENT • 4 FICHES PAR PAGE A4"
    badge_w = draw.textlength(badge_text, font=badge_font)
    badge_x = (width - badge_w) // 2
    draw.rounded_rectangle(
        [badge_x - 24, 50, badge_x + badge_w + 24, 100],
        radius=25,
        fill=(255, 228, 230, 255),
        outline=(254, 205, 211, 255),
        width=2,
    )
    draw.text((badge_x, 62), badge_text, fill=(190, 18, 60, 255), font=badge_font)

    title1_font = get_font(58, bold=True)
    title2_font = get_font(50, bold=True)
    sub_font = get_font(30, bold=False)

    t1 = "FICHES COUP DE CŒUR"
    t1_w = draw.textlength(t1, font=title1_font)
    draw.text(((width - t1_w) // 2, 125), t1, fill=(15, 23, 42, 255), font=title1_font)

    t2 = "Recommandation entre Élèves"
    t2_w = draw.textlength(t2, font=title2_font)
    draw.text(((width - t2_w) // 2, 200), t2, fill=(225, 29, 72, 255), font=title2_font)

    sub = "Fanions cartonnes a glisser dans les livres de la bibliotheque"
    sub_w = draw.textlength(sub, font=sub_font)
    draw.text(
        ((width - sub_w) // 2, 270), sub, fill=(100, 116, 139, 255), font=sub_font
    )

    # Mockup
    mockup_y0 = 350
    mockup_y1 = 1010
    card_w = 360
    gap = 40
    start_x = (width - (2 * card_w + gap)) // 2

    for idx, accent_color in enumerate([(225, 29, 72, 255), (217, 119, 6, 255)]):
        cx0 = start_x + idx * (card_w + gap)
        cx1 = cx0 + card_w

        draw_rounded_rect_with_shadow(
            draw,
            img,
            [cx0, mockup_y0, cx1, mockup_y1],
            radius=18,
            fill=(255, 255, 255, 255),
        )
        draw.rounded_rectangle(
            [cx0, mockup_y0, cx1, mockup_y1],
            radius=18,
            outline=(254, 205, 211, 255),
            width=2,
        )

        draw.rounded_rectangle(
            [cx0 + 20, mockup_y0 + 20, cx1 - 20, mockup_y0 + 80],
            radius=10,
            fill=accent_color,
        )
        t_text = "COUP DE CŒUR" if idx == 0 else "CONSEIL LECTURE"
        tf = get_font(22, bold=True)
        tw = draw.textlength(t_text, font=tf)
        draw.text(
            (cx0 + (card_w - tw) // 2, mockup_y0 + 35),
            t_text,
            fill=(255, 255, 255, 255),
            font=tf,
        )

        f_font = get_font(16, bold=True)
        draw.text(
            (cx0 + 25, mockup_y0 + 110),
            "Conseille par :",
            fill=(71, 85, 105, 255),
            font=f_font,
        )
        draw.line(
            [cx0 + 25, mockup_y0 + 150, cx1 - 25, mockup_y0 + 150],
            fill=(203, 213, 225, 255),
            width=2,
        )

        draw.text(
            (cx0 + 25, mockup_y0 + 180),
            "Titre du livre :",
            fill=(71, 85, 105, 255),
            font=f_font,
        )
        draw.line(
            [cx0 + 25, mockup_y0 + 220, cx1 - 25, mockup_y0 + 220],
            fill=(203, 213, 225, 255),
            width=2,
        )

        draw.text(
            (cx0 + 25, mockup_y0 + 250),
            "Note de l'eleve :",
            fill=(71, 85, 105, 255),
            font=f_font,
        )
        draw.text(
            (cx0 + 50, mockup_y0 + 285),
            "★ ★ ★ ★ ★",
            fill=accent_color,
            font=get_font(32, bold=True),
        )

        draw.text(
            (cx0 + 25, mockup_y0 + 350),
            "Pourquoi j'ai adore :",
            fill=(71, 85, 105, 255),
            font=f_font,
        )
        for line_idx in range(5):
            ly = mockup_y0 + 400 + line_idx * 45
            draw.line([cx0 + 25, ly, cx1 - 25, ly], fill=(226, 232, 240, 255), width=2)

        draw.text(
            (cx0 + 35, mockup_y1 - 35),
            "A laisser depasser du livre en rayon !",
            fill=(148, 163, 184, 255),
            font=get_font(13, bold=False),
        )

    bullet_box_y = 1060
    bullets = [
        "✔ Developpe l'expression critique et l'emulation de lecture",
        "✔ Fanion visible en rayon pour orienter le choix des camarades",
        "✔ 4 fiches par feuille A4 • Impression couleur ou noir & blanc",
    ]
    b_font = get_font(23, bold=True)
    for b_idx, b_text in enumerate(bullets):
        draw.text(
            (120, bullet_box_y + b_idx * 48),
            b_text,
            fill=(30, 41, 59, 255),
            font=b_font,
        )

    cta_y = 1250
    cta_w = 680
    cta_h = 90
    cta_x = (width - cta_w) // 2
    draw_rounded_rect_with_shadow(
        draw,
        img,
        [cta_x, cta_y, cta_x + cta_w, cta_y + cta_h],
        radius=45,
        fill=(225, 29, 72, 255),
        shadow_color=(225, 29, 72, 60),
    )

    cta_font = get_font(32, bold=True)
    cta_text = "📌 Epingler & Imprimer les Fiches"
    ct_text_w = draw.textlength(cta_text, font=cta_font)
    draw.text(
        (cta_x + (cta_w - ct_text_w) // 2, cta_y + 26),
        cta_text,
        fill=(255, 255, 255, 255),
        font=cta_font,
    )

    footer_font = get_font(22, bold=True)
    f_text = (
        "LIVRESENCLASSE.COM  •  L'outil de gestion de bibliotheque pour enseignants"
    )
    f_w = draw.textlength(f_text, font=footer_font)
    draw.text(
        ((width - f_w) // 2, 1390), f_text, fill=(100, 116, 139, 255), font=footer_font
    )

    output_path = OUTPUT_DIR / "fiche-de-lecture-a-imprimer.png"
    img.convert("RGB").save(output_path, "PNG", quality=95)
    print(f"Genere : {output_path}")


if __name__ == "__main__":
    create_pin_marque_pages()
    create_pin_diplome()
    create_pin_fiches_avis()
    print("Tous les visuels Pinterest 1000x1500px ont ete generes avec succes.")
