"""AI voting logic for todo sorter."""
import os
import random
import httpx
from src.parser import EmailDSLParser, Vote
from . import storage


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def make_ai_vote(list_id: str, item1: str, item2: str, criteria: str, model: str) -> str | None:
    """Ask AI to compare two items and return a DSL vote string.

    Returns:
        DSL vote string if successful, None if failed
    """
    prompt = f"""Compare these two tasks based on this criteria: "{criteria}".

Task A: /{item1}
Task B: /{item2}

You must output a single line of SorterDSL syntax.
If A is much better: /{item1} 10:1 /{item2} {{ reason }}
If A is better:     /{item1} > /{item2} {{ reason }}
If equal:           /{item1} = /{item2} {{ reason }}
If B is better:     /{item1} < /{item2} {{ reason }}
If B is much better: /{item1} 1:10 /{item2} {{ reason }}

Output ONLY the DSL line. Include a brief reason in curly braces."""

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
            resp.raise_for_status()
            result = resp.json()
            content = result['choices'][0]['message']['content'].strip()

            # Validate it's actually valid DSL by parsing it
            parser = EmailDSLParser()
            doc = parser.parse_lines(content)

            # Check that it's a vote between the expected items
            # Document has statements list, filter for Vote objects
            votes = [s for s in doc.statements if isinstance(s, Vote)]
            if votes and len(votes) == 1:
                vote = votes[0]
                if {vote.item1, vote.item2} == {item1, item2}:
                    return content

            return None

    except Exception as e:
        print(f"AI voting error: {e}")
        return None


def run_ai_sorting(list_id: str, num_votes: int = 5) -> list[dict]:
    """Run AI sorting on a todo list.

    Args:
        list_id: The todo list identifier
        num_votes: Number of pairwise comparisons to make

    Returns:
        List of vote results with details
    """
    state, meta = storage.get_todo_state(list_id)
    if not state:
        raise ValueError(f"Todo list {list_id} not found")

    items = list(state.items.keys())
    if len(items) < 2:
        raise ValueError("Need at least 2 items to compare")

    vote_results = []

    for i in range(num_votes):
        # Pick random pair
        item1, item2 = random.sample(items, 2)

        print(f"Vote {i+1}/{num_votes}: Comparing '{item1}' vs '{item2}'...")

        # Get AI vote
        vote_dsl = make_ai_vote(list_id, item1, item2, meta['criteria'], meta['model'])

        if vote_dsl:
            # Append to file
            storage.append_vote(list_id, vote_dsl)

            # Extract reason for logging
            reason = ""
            if "{" in vote_dsl and "}" in vote_dsl:
                reason = vote_dsl.split("{")[1].split("}")[0].strip()

            vote_results.append({
                "item1": item1,
                "item2": item2,
                "dsl": vote_dsl,
                "reason": reason
            })
            print(f"  → {reason}")
        else:
            print(f"  → Failed to get valid vote")
            vote_results.append({
                "item1": item1,
                "item2": item2,
                "dsl": None,
                "reason": "Failed"
            })

    return vote_results
