# User-defined classes with same names - should NOT be detected
import my_billing_framework


class OpenAI:
    def __init__(self, api_key: str = "") -> None:
        pass


class ChatCompletion:
    @classmethod
    def create(cls, model: str = "", messages: list | None = None, **kwargs):
        return {"choices": [{"message": {"content": "custom response"}}]}


class Completion:
    @classmethod
    def create(cls, model: str = "", prompt: str = "", **kwargs):
        return {"choices": [{"text": "custom completion"}]}


# Usage of user's own classes - should NOT be flagged
my_client = OpenAI()
result = my_client.ChatCompletion.create(model="my-model", messages=[])

# Should NOT be detected as Stripe
charge = my_billing_framework.Charge.create(amount=100)

# Strings and comments - should NOT be detected
DOC = """
You can use openai.ChatCompletion.create() or stripe.Charge.create()
"""

msg = "openai.ChatCompletion.create(model='gpt-4')"
log_entry = "stripe.Charge.create"

# Dynamic calls - should NOT be detected (static analysis limitation)
method = "chat.completions.create"
client = object()  # dummy object
getattr(client, method)(model="gpt-4o")  # client not defined, but pattern exists
