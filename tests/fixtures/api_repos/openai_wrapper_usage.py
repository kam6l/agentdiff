import openai

client = openai.OpenAI()


# Wrapper function - indirect usage
def ask_openai(prompt: str, model: str = "gpt-4o") -> str:
    """Wrapper around OpenAI chat completions."""
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


# Another wrapper with different signature
def ask_with_context(prompt: str, context: str = "") -> str:
    messages = [{"role": "user", "content": prompt}]
    if context:
        messages.insert(0, {"role": "system", "content": context})
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
    )
    return response.choices[0].message.content


# Class-based wrapper
class AIService:
    def __init__(self):
        self.client = openai.OpenAI()

    def ask(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
