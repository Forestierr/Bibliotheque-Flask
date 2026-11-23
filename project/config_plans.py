"""
config_plans.py: Configuration centralisée des quotas freemium, de la tarification et de la période d'essai.
Modifier ces constantes permet d'ajuster l'ensemble des règles de l'application en un seul endroit.
"""

# Quotas et limites du plan gratuit (Free)
MAX_FREE_STUDENTS = 30
MAX_FREE_BOOKS = 100
MAX_FREE_SCANS = (
    30  # 30 scans de codes-barres par semaine (remis à zéro chaque dimanche à 00:00:00)
)
FREE_HISTORY_MONTHS = 10
TRIAL_PERIOD_DAYS = 0

# Devise et tarification
DEFAULT_CURRENCY = "CHF"
PRICE_MONTHLY_AMOUNT = 3.0
PRICE_YEARLY_AMOUNT = 30.0
PRICE_YEARLY_EUR_AMOUNT = 30.0

# Mention fiscale légale suisse (Art. 10 LTVA) pour factures et reçus Stripe
STRIPE_TAX_EXEMPTION_NOTICE = (
    "Prestation de services de logiciel éducatif. "
    "Exonéré de TVA selon l'art. 10 de la Loi fédérale suisse régissant la taxe sur la valeur ajoutée (LTVA). "
    "Montant net à payer."
)

# Seuil d'alerte pour les jauges visuelles (en pourcentage)
GAUGE_WARNING_PERCENT = 80

# Code promotionnel proposé lors d'une tentative de suppression de compte (rétention)
RETENTION_PROMO_CODE = "PROMO30"

