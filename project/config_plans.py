"""
config_plans.py: Configuration centralisée des quotas freemium, de la tarification et de la période d'essai.
Modifier ces constantes permet d'ajuster l'ensemble des règles de l'application en un seul endroit.
"""

# Quotas et limites du plan gratuit (Free)
MAX_FREE_STUDENTS = 40
MAX_FREE_BOOKS = 500
MAX_FREE_SCANS = (
    30  # 30 scans de codes-barres par semaine (remis à zéro chaque dimanche à 00:00:00)
)
FREE_HISTORY_MONTHS = 10
TRIAL_PERIOD_DAYS = 0

# Devise et tarification
DEFAULT_CURRENCY = "CHF"
PRICE_MONTHLY_AMOUNT = 5.0
PRICE_YEARLY_AMOUNT = 30.0

# Seuil d'alerte pour les jauges visuelles (en pourcentage)
GAUGE_WARNING_PERCENT = 80
