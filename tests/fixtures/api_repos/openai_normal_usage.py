import openai

client = openai.OpenAI(api_key="sk-test")


def ask_gpt(prompt: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def ask_with_tools(prompt: str, tools: list) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        tools=tools,
    )
    return response.choices[0].message.content
