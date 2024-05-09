import openai

import vocode


def openai_embed(text: str) -> list:
    client = openai.AzureOpenAI(
        api_key=vocode.getenv('AZURE_OPENAI_API_KEY'),
        api_version="2023-03-15-preview",
        base_url=vocode.getenv('AZURE_OPENAI_API_BASE')
    )

    return openai.Embedding.create(engine='text-embedding-ada-002', input=text).data[0].embedding
