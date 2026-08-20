import stripe

stripe.api_key = "sk_test_123"


def charge_customer(token: str, amount_cents: int) -> dict:
    return stripe.Charge.create(
        amount=amount_cents,
        currency="usd",
        source=token,
        description="Test charge",
    )


def create_payment_intent(amount: int, currency: str = "usd") -> dict:
    return stripe.PaymentIntent.create(
        amount=amount,
        currency=currency,
        automatic_payment_methods={"enabled": True},
    )


def create_customer(email: str) -> dict:
    return stripe.Customer.create(email=email)


def list_prices(product_id: str) -> dict:
    return stripe.Price.list(product=product_id)
