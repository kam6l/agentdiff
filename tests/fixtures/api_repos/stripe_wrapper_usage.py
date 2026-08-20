import stripe

stripe.api_key = "sk_test_123"


# Wrapper functions
def process_payment(token: str, amount: int, currency: str = "usd") -> dict:
    """Wrapper around Stripe Charge.create - LEGACY."""
    return stripe.Charge.create(
        amount=amount,
        currency=currency,
        source=token,
    )


def create_subscription(customer_id: str, price_id: str) -> dict:
    """Wrapper around Stripe Subscription.create."""
    return stripe.Subscription.create(
        customer=customer_id,
        items=[{"price": price_id}],
    )


# Class-based wrapper
class PaymentService:
    def __init__(self):
        self.stripe = stripe

    def charge(self, token: str, amount: int) -> dict:
        return self.stripe.Charge.create(
            amount=amount,
            currency="usd",
            source=token,
        )
