# Bibliotheque flask

[Version française](README.md)

<strong>My Bibliotheque</strong> is a web application specifically designed to meet the needs of teachers in managing 
their classroom library. This intuitive platform allows them to easily centralise and organise their book collection.
They can add new books, modify existing information or delete books that are no longer needed. What's more, the 
application provides detailed information on the books borrowed by their students, so they know which books have been 
borrowed, by whom and for how long. Thanks to LivresEnClasse.com, teachers can encourage reading while keeping a clear 
and precise overview of the use of their library's resources.

> [!NOTE]
> This document has been translated from French to English using [DeepL](https://www.deepl.com/translator).

## Features

- Add, delete, modify a book
- Add, delete or modify a student
- Scan a book's barcode
- Borrowing management
- Login / logout

## Installation

### Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

Then install the dependencies:

```bash
pip install -r project/requirements.txt
```

Modify the `.env' file to set the environment variables.
The `.env.example` file has all the default values, you just need to copy the file and add your 
copy the file and add your own values.

```bash
cp .env.example .env
```

### Create the database

```bash
flask db init
flask db migrate
flask db upgrade
```

> [!TIP]
> You can use the `flask db --help` command to see all available commands.

### Update the database

If you change the data model, you must update the database.

```bash
flask db migrate -m "message"
flask db upgrade
```

### Run the server

```bash
$env:FLASK_APP = "project"
flask run -p 80 -h 0.0.0.0
```

And go to http://127.0.0.1:80

> [!TIP]
> You can use the `flask run --help` command to see all available options.

> [!CAUTION]
> Flask does not launch a WSGI server, you must use a production WSGI server like Gunicorn.

If you have any problems developing with the scanner.
You may need to use an HTTPS server.
To do this, you can use the `--cert=adhoc` flag.


## Stripe Integration & Local Testing with Stripe CLI

The application integrates Stripe Checkout and the Stripe Customer Portal for the Premium subscription tier.

### 1. Environment Variables (.env)

Add your Stripe test credentials to `.env`:

```bash
STRIPE_PUBLIC_KEY='pk_test_...'
STRIPE_SECRET_KEY='sk_test_...'
STRIPE_WEBHOOK_SECRET='whsec_...'
STRIPE_PRICE_MONTHLY='price_...'  # Monthly price ID (5.- CHF/month)
STRIPE_PRICE_YEARLY='price_...'   # Annual price ID (30.- CHF/year)
```

### 2. Installing Stripe CLI

The **Stripe CLI** allows forwarding live Stripe test webhook events directly to your local Flask server.

- **Windows**: `scoop install stripe` or `choco install stripe-cli` or download `stripe.exe` from [GitHub Releases](https://github.com/stripe/stripe-cli/releases).
- **macOS**: `brew install stripe/stripe-cli/stripe`
- **Linux**: Install official `.deb` or `.rpm` packages.

### 3. Authenticate Stripe CLI

```bash
stripe login
```

### 4. Forwarding Webhooks Locally

Run webhook listening forwarding to your Flask port (default 5000):

```bash
stripe listen --forward-to localhost:5000/webhook/stripe
```

Copy the printed webhook signing secret `whsec_...` into `.env` under `STRIPE_WEBHOOK_SECRET`.

### 5. Triggering Test Events

In another terminal, trigger simulated events:

```bash
# Completed checkout & subscription activation
stripe trigger checkout.session.completed

# Subscription updated
stripe trigger customer.subscription.updated

# Subscription deleted / canceled (with 48h grace period & email notification)
stripe trigger customer.subscription.deleted

# Payment failed (email notification to update card)
stripe trigger invoice.payment_failed
```

### 6. In-Browser Checkout & Stripe Test Cards

- Visit `http://localhost:5000/tarifs`
- Select either plan to access the order summary at `/paiement`.
- Click "Procéder au paiement sécurisé" to open Stripe Checkout.
- After validation, you are redirected to `/subscription/success` and the account is upgraded to Premium.

#### Stripe Test Cards

Test mode (using your `sk_test_...` keys) is completely disconnected from the actual banking network. To validate payments and test the integration flow, exclusively use fake card numbers provided by Stripe:

- **Successful payment (most common)**: `4242 4242 4242 4242`
- **Declined payment (insufficient funds)**: `4000 0000 0000 0002`
- **Declined payment (lost/stolen card)**: `4000 0000 0000 0022`
- **Payment requiring 3D Secure authentication**: `4000 0000 0000 3020`

For expiration date, enter any date in the future (e.g. `12/30`).  
For CVC, enter any 3 digits (e.g. `123`).

### 7. Customer Portal

A Premium user can manage payment methods, download invoices or cancel anytime:
- Directly at `http://localhost:5000/portail-abonne`
- Or via "Gérer mon abonnement" in settings (`/reglage`) and `/tarifs`.

### 8. Idempotency & CSRF Exemption

- The `/webhook/stripe` route is decorated with `@csrf.exempt` to ensure Stripe webhook requests bypass Flask-WTF CSRF validation.
- All webhook event handlers implement idempotent state checks to safely handle duplicate webhook deliveries.


## Published

To publish the application, I decided to use [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
nginx and gunicorn. This allows me to publish the application on my personal server and make it accessible under
a custom domain name [Cloudflare Registrar](https://www.cloudflare.com/fr-fr/products/registrar/).

To do this I took inspiration from the blog post by [austinsnerdythings](https://austinsnerdythings.com/2023/11/01/using-github-actions-to-deploy-a-flask-nginx-cloudflared-tunnel-docker-compose-stack/).
But without using GitHub Actions, you're free to use it.

> [!CAUTION]
> This solution does not automatically make your application secure. You still need to focus on security. Any vulnerability in your web application could allow an attacker to gain a foothold in your network. Your Docker host should be isolated from the rest of your network by a firewall as a first step to prevent intrusion into other computers/services/systems on your network. All subsequent steps should focus on the usual attack vectors (SQL injection, system updates, etc.).

### Infrastructure diagram

![Infrastructure schema](docs/infrastructure.png)

## Launch the application

Firstly, you need to create a `docker-compose.yml` file at the root of the project.

```yaml
command: tunnel --no-autoupdate run --token ${CF_TOCKEN}
```

By replacing `${CF_TOCKEN}` with your Cloudflare token.

### Build and launch the application

```bash
docker-compose up --build
```

> [!TIP]
> You can use the `-d` option to launch containers in the background.

### Stop the application

```bash
docker-compose down
```

## Database

The database is a SQLite database. Stored in the `instance\db.sqlite` file.

### Database schema

![Database schema](docs/model.png)

_The **User** is a professor._

## License

This project is licensed under the MIT licence - see the [LICENSE](LICENSE.md) file for more details.

##


