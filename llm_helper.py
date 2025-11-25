import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI()
MODEL_NAME = "gpt-3.5-turbo"

def call_llm(system_prompt: str, user_content: str) -> str:
    """
    Generic helper to call the LLM and return the assistant's message content.
    """
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
    )
    return response.choices[0].message.content

def call_llm_json(system_prompt: str, user_content: str):
    """
    Calls the LLM and tries to parse JSON from the response.
    If parsing fails, returns None.
    """
    text = call_llm(system_prompt, user_content)
    try:
        # Try to extract JSON from the text (in case model adds extra text)
        start = text.find("{")
        if start == -1:
            start = text.find("[")
        if start != -1:
            json_part = text[start:]
            return json.loads(json_part)
        return json.loads(text)
    except Exception:
        return None
