from openai import OpenAI

client = OpenAI()


def answer(question: str) -> str:
    response = client.chat.completions.create(
        model="gpt-5.5",
        messages=[{"role": "user", "content": question}],
        max_tokens=120,
        store=False,
    )
    return response.choices[0].message.content
