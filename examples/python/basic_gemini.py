"""Example: inspect Gemini function calling with TraceLoom.

Set GEMINI_API_KEY, then run:
    traceloom run examples/python/basic_gemini.py
"""

from google import genai
from google.genai import types


def get_order_status(order_id: str) -> dict[str, str]:
    """Return the current status of an order."""
    return {
        "order_id": order_id,
        "status": "shipped",
        "estimated_delivery": "2026-07-30",
    }


client = genai.Client()
response = client.models.generate_content(
    model="gemini-3.5-flash",
    contents="Where is order 1042?",
    config=types.GenerateContentConfig(
        system_instruction="Use the order tool before answering.",
        tools=[get_order_status],
    ),
)

print(response.text)
