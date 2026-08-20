"""Stripe API provider detection and breaking change catalog."""

from __future__ import annotations

from agentdiff.api.models import APIChange, ChangeSeverity, ChangeType
from agentdiff.api.providers.base import APIProvider


class StripeProvider(APIProvider):
    """Provider for Stripe Python SDK."""

    @property
    def name(self) -> str:
        return "stripe"

    @property
    def library(self) -> str:
        return "stripe"

    @property
    def import_names(self) -> frozenset[str]:
        return frozenset({"stripe"})

    def get_known_changes(self) -> list[APIChange]:
        return [
            APIChange(
                change_id="stripe-charges-to-payment-intents",
                provider="stripe",
                title="Legacy stripe.Charge.create deprecated in favor of PaymentIntents API",
                change_type=ChangeType.DEPRECATION,
                severity=ChangeSeverity.HIGH,
                target_symbol="stripe.Charge.create",
                target_symbols=("stripe.Charge.create", "client.charges.create"),
                description=(
                    "Direct `stripe.Charge.create()` calls do not support Strong Customer"
                    " Authentication (SCA) or 3D Secure 2."
                    " Migrate to `stripe.PaymentIntent.create()`."
                ),
                migration_guide_url="https://stripe.com/docs/payments/payment-intents/migration",
                replacement_symbol="stripe.PaymentIntent.create",
                replacement_code=(
                    "intent = stripe.PaymentIntent.create(\n"
                    "    amount=2000,\n"
                    "    currency='usd',\n"
                    "    automatic_payment_methods={'enabled': True},\n"
                    ")"
                ),
            ),
            APIChange(
                change_id="stripe-sources-to-payment-methods",
                provider="stripe",
                title="Legacy stripe.Source.create deprecated in favor of PaymentMethods",
                change_type=ChangeType.DEPRECATION,
                severity=ChangeSeverity.HIGH,
                target_symbol="stripe.Source.create",
                target_symbols=("stripe.Source.create", "client.sources.create"),
                description=(
                    "`stripe.Source.create()` is legacy. Migrate to `stripe.PaymentMethod.create()`"
                    " and `stripe.SetupIntent.create()`."
                ),
                migration_guide_url="https://stripe.com/docs/payments/payment-methods/transitioning",
                replacement_symbol="stripe.PaymentMethod.create",
                replacement_code=(
                    "pm = stripe.PaymentMethod.create(type='card', card={'token': 'tok_visa'})"
                ),
            ),
            APIChange(
                change_id="stripe-tokens-deprecated",
                provider="stripe",
                title="Legacy stripe.Token.create deprecated for direct card handling",
                change_type=ChangeType.DEPRECATION,
                severity=ChangeSeverity.MODERATE,
                target_symbol="stripe.Token.create",
                target_symbols=("stripe.Token.create", "client.tokens.create"),
                description=(
                    "Creating raw card tokens with `stripe.Token.create()` is legacy and incurs"
                    " higher PCI compliance burden. Migrate to Stripe Elements and PaymentMethods."
                ),
                migration_guide_url="https://stripe.com/docs/payments/payment-methods",
                replacement_symbol="stripe.PaymentMethod.create",
                replacement_code=(
                    "intent = stripe.PaymentIntent.create(amount=amount, currency=currency)"
                ),
            ),
            APIChange(
                change_id="stripe-plans-to-prices",
                provider="stripe",
                title="Legacy stripe.Plan.create deprecated in favor of stripe.Price.create",
                change_type=ChangeType.DEPRECATION,
                severity=ChangeSeverity.MODERATE,
                target_symbol="stripe.Plan.create",
                target_symbols=("stripe.Plan.create", "client.plans.create"),
                description=(
                    "`stripe.Plan.create()` has been unified under the Prices API."
                    " Use `stripe.Price.create()`."
                ),
                migration_guide_url="https://stripe.com/docs/products-prices/overview",
                replacement_symbol="stripe.Price.create",
                replacement_code=(
                    "price = stripe.Price.create(\n"
                    "    unit_amount=2000,\n"
                    "    currency='usd',\n"
                    "    recurring={'interval': 'month'},\n"
                    "    product=product_id,\n"
                    ")"
                ),
            ),
            APIChange(
                change_id="stripe-orders-deprecated",
                provider="stripe",
                title="Legacy stripe.Order.create removed in favor of PaymentIntents & Checkout",
                change_type=ChangeType.REMOVAL,
                severity=ChangeSeverity.CRITICAL,
                target_symbol="stripe.Order.create",
                target_symbols=("stripe.Order.create", "client.orders.create"),
                description=(
                    "The legacy `stripe.Order` API was deprecated and removed."
                    " Use Stripe Checkout Sessions or PaymentIntents."
                ),
                migration_guide_url="https://stripe.com/docs/payments/checkout",
                replacement_symbol="stripe.checkout.Session.create",
                replacement_code=(
                    "session = stripe.checkout.Session.create(\n"
                    "    line_items=[{'price': price_id, 'quantity': 1}],\n"
                    "    mode='payment',\n"
                    "    success_url=success_url,\n"
                    "    cancel_url=cancel_url,\n"
                    ")"
                ),
            ),
            APIChange(
                change_id="stripe-skus-deprecated",
                provider="stripe",
                title="Legacy stripe.SKU.create deprecated in favor of Products & Prices",
                change_type=ChangeType.DEPRECATION,
                severity=ChangeSeverity.MODERATE,
                target_symbol="stripe.SKU.create",
                target_symbols=("stripe.SKU.create", "client.skus.create"),
                description=(
                    "`stripe.SKU.create()` is deprecated. Model items using"
                    " `stripe.Product.create()` and `stripe.Price.create()`."
                ),
                migration_guide_url="https://stripe.com/docs/products-prices/overview",
                replacement_symbol="stripe.Price.create",
                replacement_code=(
                    "price = stripe.Price.create(\n"
                    "    unit_amount=1000, currency='usd', product=product_id\n"
                    ")"
                ),
            ),
            APIChange(
                change_id="stripe-deprecated-card-parameter",
                provider="stripe",
                title="Legacy `card` parameter deprecated in Charge creation",
                change_type=ChangeType.PARAMETER_REMOVAL,
                severity=ChangeSeverity.HIGH,
                target_symbol="stripe.Charge.create",
                target_symbols=("stripe.Charge.create", "client.charges.create"),
                target_parameter="card",
                description=(
                    "Passing raw `card` dictionary or token into `stripe.Charge.create()` is"
                    " deprecated. Use PaymentIntents with `payment_method`."
                ),
                migration_guide_url="https://stripe.com/docs/payments/payment-intents",
                replacement_symbol="payment_method",
                replacement_code=(
                    "intent = stripe.PaymentIntent.create(\n"
                    "    amount=amount, currency='usd', payment_method=pm_id\n"
                    ")"
                ),
            ),
        ]
