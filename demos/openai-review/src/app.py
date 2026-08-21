from openai import OpenAI

client = OpenAI()


def build_messages(question: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": question}]


def answer(question: str) -> str:
    response = client.chat.completions.create(
        model="gpt-5.5",
        messages=build_messages(question),
    )
    return response.choices[0].message.content
