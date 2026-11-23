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

# Mentions fiscales légales obligatoires (B2B Écoles & Mairies)
STRIPE_TAX_NOTICE_EU = (
    "Prestation de services de logiciel éducatif. "
    "Exonération de TVA – Autoliquidation par le preneur (art. 196 de la directive 2006/112/CE). "
    "Prix Hors Taxes (HT) : montant net identique au TTC."
)

STRIPE_TAX_NOTICE_CH = (
    "Prestation de services de logiciel éducatif. "
    "Non assujetti à la TVA (art. 10 LTVA). "
    "Montant net Hors Taxes (HT) à payer."
)

# Rétro-compatibilité
STRIPE_TAX_EXEMPTION_NOTICE = STRIPE_TAX_NOTICE_CH


def get_stripe_tax_notice(currency="CHF"):
    """Retourne la mention fiscale légale adaptée à la devise / juridiction."""
    if str(currency).upper() == "EUR":
        return STRIPE_TAX_NOTICE_EU
    return STRIPE_TAX_NOTICE_CH

# Seuil d'alerte pour les jauges visuelles (en pourcentage)
GAUGE_WARNING_PERCENT = 80

# Code promotionnel proposé lors d'une tentative de suppression de compte (rétention)
RETENTION_PROMO_CODE = "PROMO30"

