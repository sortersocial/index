"""AI logic for conversational todo sorter."""
import os
import json
import httpx
from typing import AsyncGenerator

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You are Sorter, an intelligent assistant that helps users think and prioritize using SorterDSL.

Your Goal: Help the user organize their thoughts. As you chat, you must capture the state of the world using DSL commands.

The DSL Syntax:
- Define items: /item-name { optional description }
- Context/Criteria: :urgency (or :cost, :impact, etc)
- Votes: /item1 > /item2 { reason } or /item1 < /item2 or /item1 = /item2
- Hashtags: #project-name

Important Rules:
1. Speak naturally to the user in conversational prose.
2. Interweave DSL commands into your response when the user mentions new tasks or preferences.
3. If the user is vague, ask clarifying questions or propose a criteria.
4. If the user says "I like X more than Y", immediately output a vote: `/X > /Y { user preference }`.
5. If the user mentions a list of things, define them as items with `/item-name`.
6. Item names MUST be lowercase with hyphens instead of spaces (e.g., /fix-bug not /Fix Bug).
7. When you write DSL, put it on its own line for clarity.

Example Output:
"That sounds stressful. Let's capture those tasks.

#launch-party

/book-venue { need capacity for 50 }
/order-food

Since you said the venue is the bottleneck, let's prioritize that:

:urgency

/book-venue > /order-food { venue availability affects timeline }"
"""


async def chat_with_ai(current_content: str, user_message: str, model: str) -> AsyncGenerator[str, None]:
    """
    Stream a response from the AI based on the current file content and new user message.

    Args:
        current_content: The full .sorter file content so far
        user_message: The latest message from the user
        model: The AI model to use

    Yields:
        Chunks of the AI response as they arrive
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Here is the current conversation/file state:\n\n---\n{current_content}\n---\n\nThe user just said: {user_message}"
        }
    ]

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True
                }
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            json_data = json.loads(data)
                            content = json_data['choices'][0]['delta'].get('content', '')
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
    except Exception as e:
        yield f"\n[Error contacting AI: {e}]\n"
