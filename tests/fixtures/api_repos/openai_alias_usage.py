import openai as oai
from openai import OpenAI as OAIClient

client = OAIClient()

# Direct call using the client variable - should be detected
result = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hello"}],
)


def chat(oai_client):
    return oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
    )


def legacy_chat():
    return oai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "legacy"}],
    )
