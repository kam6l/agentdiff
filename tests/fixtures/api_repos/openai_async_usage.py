import openai

client = openai.AsyncOpenAI()


async def ask_gpt_async(prompt: str) -> str:
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


async def stream_gpt(prompt: str):
    stream = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    async for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


async def embeddings_async(texts: list[str]):
    return await client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
