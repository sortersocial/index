"""FastAPI routes for AI todo sorter."""
import asyncio
from typing import AsyncGenerator
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from python_hiccup.html.core import render as hiccup_render
from datastar_py import ServerSentEventGenerator
from . import ui, storage, ai_voter
from src.rank import compute_rankings_from_state


router = APIRouter(prefix="/todo")


@router.get("/", response_class=HTMLResponse)
async def index():
    """Show the create form and list of existing conversations."""
    # Get all existing conversations
    import os
    from pathlib import Path

    conversations = []
    todo_dir = storage.TODO_DIR
    if todo_dir.exists():
        for file in sorted(todo_dir.glob("*.sorter"), key=os.path.getmtime, reverse=True):
            list_id = file.stem
            # Get metadata
            try:
                state, meta = storage.get_todo_state(list_id)
                item_count = len(state.items) if state else 0
                conversations.append({
                    "id": list_id,
                    "model": meta.get("model", "unknown") if meta else "unknown",
                    "item_count": item_count,
                    "modified": file.stat().st_mtime
                })
            except:
                # Skip corrupted files
                continue

    return ui.layout(ui.create_form(conversations))


@router.post("/create")
async def create(request: Request):
    """Create a new chat session and redirect to it."""
    data = await request.json()

    # Extract from datastar signal object if present
    if "datastar" in data:
        data = data["datastar"]

    message = data.get("message", "").strip()
    model = data.get("model", "anthropic/claude-3.5-haiku")

    if not message:
        return HTMLResponse("Need a message to start", status_code=400)

    # Create an empty list with default criteria
    list_id = storage.create_todo_list([], "general", model)

    # Append the initial user message
    storage.append_raw(list_id, f"\n---USER---\n{message}\n")

    # Return SSE event to redirect using datastar-py
    sse = ServerSentEventGenerator()
    return StreamingResponse(
        iter([sse.execute_script(f"window.location = '/todo/{list_id}'")]),
        media_type="text/event-stream"
    )


def parse_conversation_history(raw_content: str):
    """Parse conversation history from .sorter file into message bubbles.

    Returns hiccup data structure with all message bubbles.
    """
    from src.render import render_email_body_hiccup
    import re

    # Split on message markers
    messages = []
    current_role = None
    current_content = []

    for line in raw_content.split('\n'):
        if line.strip() == '---USER---':
            # Save previous message if any
            if current_role and current_content:
                content_text = '\n'.join(current_content).strip()
                if content_text:
                    messages.append((current_role, content_text))
            current_role = 'user'
            current_content = []
        elif line.strip() == '---AI---':
            # Save previous message if any
            if current_role and current_content:
                content_text = '\n'.join(current_content).strip()
                if content_text:
                    messages.append((current_role, content_text))
            current_role = 'ai'
            current_content = []
        elif line.strip() == '---':
            # Skip the metadata separator
            continue
        elif current_role:
            current_content.append(line)

    # Save last message
    if current_role and current_content:
        content_text = '\n'.join(current_content).strip()
        if content_text:
            messages.append((current_role, content_text))

    # Render each message as a bubble
    bubbles = []
    for role, content in messages:
        if role == 'user':
            # User messages are plain text
            bubble = ui.message_bubble(role, content)
        else:
            # AI messages may contain DSL, render them
            content_hiccup = render_email_body_hiccup(content)
            bubble = ui.message_bubble(role, content_hiccup)
        bubbles.append(bubble)

    # Return as raw HTML fragments joined together
    return ''.join(bubbles)


@router.get("/{list_id}", response_class=HTMLResponse)
async def view_chat(list_id: str, attribute: str = None):
    """View the chat interface."""
    from collections import Counter

    state, meta = storage.get_todo_state(list_id)
    if not state:
        return HTMLResponse("Not found", status_code=404)

    # Parse and render conversation history as message bubbles
    raw_content = storage.get_file_path(list_id).read_text(encoding="utf-8")
    history_html = parse_conversation_history(raw_content)

    # Collect all available attributes from votes
    attribute_counts = Counter()
    for vote in state.votes:
        if vote.attribute:
            attribute_counts[vote.attribute] += 1

    available_attributes = sorted(attribute_counts.items(), key=lambda x: x[1], reverse=True)

    # Use requested attribute, or default to most common, or fallback to meta criteria
    if attribute is None and available_attributes:
        attribute = available_attributes[0][0]
    elif attribute is None:
        attribute = meta['criteria'].replace(" ", "-")

    # Render rankings as hiccup data
    rankings = compute_rankings_from_state(
        state,
        f"todo-{list_id}",
        attribute
    )

    # Group by component and only show connected components (size > 1)
    from collections import defaultdict
    components_dict = defaultdict(list)
    for title, score, rank, comp_id in rankings:
        components_dict[comp_id].append((title, score, rank))

    # Filter to only components with multiple items (strongly connected)
    display_items = []
    for comp_id, items in sorted(components_dict.items()):
        if len(items) > 1:
            display_items.extend(items)

    rankings_hiccup = ui.rankings_fragment(display_items, meta, available_attributes, attribute)

    return ui.layout(ui.chat_view(list_id, history_html, rankings_hiccup, meta))


@router.post("/{list_id}/chat")
async def chat_interaction(request: Request, list_id: str):
    """
    Handle chat message:
    1. Append user msg to file
    2. Stream back user bubble
    3. Trigger AI
    4. Stream AI chunks (and append to file)
    5. Update rankings side-effect
    """
    from src.render import render_email_body

    data = await request.json()
    if "datastar" in data:
        data = data["datastar"]

    user_message = data.get("message", "")

    if not user_message.strip():
        return StreamingResponse(iter([]), media_type="text/event-stream")

    # Append user message to file
    user_block = f"\n\n---USER---\n{user_message}\n"
    storage.append_raw(list_id, user_block)

    async def stream_response():
        from src.render import render_email_body_hiccup
        sse = ServerSentEventGenerator()

        # Render user bubble (immediate UI feedback)
        user_html = ui.message_bubble("user", user_message)
        yield sse.patch_elements(
            elements=user_html,
            selector="#chat-history",
            mode="append"
        )

        # Get context and stream AI
        current_content = storage.get_file_path(list_id).read_text(encoding="utf-8")
        state, meta = storage.get_todo_state(list_id)

        ai_accumulated = ""

        # Start AI bubble (thinking indicator)
        thinking_html = hiccup_render([
            'div', {'id': 'ai-typing', 'class': 'message ai', 'style': 'display: flex; flex-direction: column; align-items: flex-start; margin-bottom: 15px;'},
            ['div', {'style': 'background: #f5f5f5; padding: 10px 15px; border-radius: 12px; max-width: 90%;'},
                ['em', 'Thinking...']
            ]
        ])

        yield sse.patch_elements(
            elements=thinking_html,
            selector="#chat-history",
            mode="append"
        )

        # Stream AI tokens
        async for chunk in ai_voter.chat_with_ai(current_content, user_message, meta['model']):
            ai_accumulated += chunk

            # Render current accumulation as hiccup data
            rendered_hiccup = render_email_body_hiccup(ai_accumulated)

            bubble_html = ui.message_bubble("ai", rendered_hiccup, bubble_id="ai-typing")

            yield sse.patch_elements(
                elements=bubble_html,
                selector="#ai-typing",
                mode="outer"  # Replace the whole element
            )

        # Commit AI response to file
        storage.append_raw(list_id, f"\n---AI---\n{ai_accumulated}\n")

        # Update rankings (the side effect!)
        # Re-parse the file now that AI wrote DSL
        from collections import Counter
        new_state, _ = storage.get_todo_state(list_id)

        # Collect available attributes from the new state
        attribute_counts = Counter()
        for vote in new_state.votes:
            if vote.attribute:
                attribute_counts[vote.attribute] += 1

        available_attributes = sorted(attribute_counts.items(), key=lambda x: x[1], reverse=True)

        # Use most common attribute or fallback
        if available_attributes:
            current_attribute = available_attributes[0][0]
        else:
            current_attribute = meta['criteria'].replace(" ", "-")

        new_rankings = compute_rankings_from_state(
            new_state,
            f"todo-{list_id}",
            current_attribute
        )

        # Group by component and only show connected components (size > 1)
        from collections import defaultdict
        components_dict = defaultdict(list)
        for title, score, rank, comp_id in new_rankings:
            components_dict[comp_id].append((title, score, rank))

        # Filter to only components with multiple items (strongly connected)
        display_items = []
        for comp_id, items in sorted(components_dict.items()):
            if len(items) > 1:
                display_items.extend(items)

        rankings_hiccup = ui.rankings_fragment(display_items, meta, available_attributes, current_attribute)
        rankings_html = hiccup_render(rankings_hiccup)

        yield sse.patch_elements(
            elements=rankings_html,
            selector="#rankings-view",
            mode="outer"
        )

        # Scroll chat to bottom
        yield sse.execute_script("document.getElementById('chat-history').scrollTop = document.getElementById('chat-history').scrollHeight")

    return StreamingResponse(stream_response(), media_type="text/event-stream")


async def ai_sorter_stream(list_id: str) -> AsyncGenerator[str, None]:
    """
    SSE stream generator that runs AI sorting and yields updates.

    Yields SSE events in the format:
        event: datastar-fragment
        data: <html fragment>

    """
    NUM_VOTES = 5  # Fixed number of votes for now

    vote_log = []

    for i in range(NUM_VOTES):
        # Load current state
        state, meta = storage.get_todo_state(list_id)
        items = list(state.items.keys())

        if len(items) < 2:
            break

        # Pick random pair
        import random
        item1, item2 = random.sample(items, 2)

        # Get AI vote
        vote_dsl = ai_voter.make_ai_vote(
            list_id, item1, item2,
            meta['criteria'],
            meta['model']
        )

        if vote_dsl:
            # Append to file
            storage.append_vote(list_id, vote_dsl)

            # Extract reason
            reason = ""
            if "{" in vote_dsl and "}" in vote_dsl:
                reason = vote_dsl.split("{")[1].split("}")[0].strip()

            vote_log.append({
                "item1": item1,
                "item2": item2,
                "reason": reason
            })

            # Recompute rankings
            new_state, _ = storage.get_todo_state(list_id)
            rankings = compute_rankings_from_state(
                new_state,
                f"todo-{list_id}",
                meta['criteria'].replace(" ", "-")
            )
            display_items = [(title, score, rank) for title, score, rank, _ in rankings]

            # Render updated view
            new_html = hiccup_render(
                ui.ranking_view(list_id, display_items, meta, vote_log, is_streaming=True)
            )

            # Use datastar-py to create proper SSE event
            sse = ServerSentEventGenerator()
            yield sse.patch_elements(
                elements=new_html,
                selector="#ranking-container",
                mode="outer"  # Replace entire element including wrapper
            )

        # Rate limiting - be polite to API and allow visual updates
        await asyncio.sleep(1.5)

    # Final update: mark as complete
    state, meta = storage.get_todo_state(list_id)
    rankings = compute_rankings_from_state(
        state,
        f"todo-{list_id}",
        meta['criteria'].replace(" ", "-")
    )
    display_items = [(title, score, rank) for title, score, rank, _ in rankings]

    final_html = hiccup_render(
        ui.ranking_view(list_id, display_items, meta, vote_log, is_streaming=False)
    )

    sse = ServerSentEventGenerator()
    yield sse.patch_elements(
        elements=final_html,
        selector="#ranking-container",
        mode="outer"
    )


@router.get("/{list_id}/stream")
async def stream_processing(list_id: str):
    """SSE endpoint for live ranking updates."""
    return StreamingResponse(
        ai_sorter_stream(list_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
