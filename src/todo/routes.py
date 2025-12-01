"""FastAPI routes for AI todo sorter."""
import asyncio
from typing import AsyncGenerator
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from python_hiccup.html.core import render as hiccup_render
from . import ui, storage, ai_voter
from src.rank import compute_rankings_from_state


router = APIRouter(prefix="/todo")


@router.get("/", response_class=HTMLResponse)
async def index():
    """Show the create form."""
    return ui.layout(ui.create_form())


@router.post("/create")
async def create(request: Request):
    """Create a new todo list and redirect to it."""
    data = await request.json()
    items = [line.strip() for line in data.get("items", "").split("\n") if line.strip()]
    criteria = data.get("criteria", "Importance")
    model = data.get("model", "anthropic/claude-3.5-haiku")

    if not items or len(items) < 2:
        return HTMLResponse("Need at least 2 items", status_code=400)

    list_id = storage.create_todo_list(items, criteria, model)

    # Datastar redirect (client-side URL change)
    return HTMLResponse(
        "",
        headers={"Datastar-Redirect": f"/todo/{list_id}"}
    )


@router.get("/{list_id}", response_class=HTMLResponse)
async def view_list(list_id: str):
    """View a todo list (initial render before streaming)."""
    state, meta = storage.get_todo_state(list_id)
    if not state:
        return HTMLResponse("Not found", status_code=404)

    # Initial ranking (all equal scores)
    rankings = compute_rankings_from_state(
        state,
        f"todo-{list_id}",
        meta['criteria'].replace(" ", "-")
    )

    # Format for display
    display_items = [(title, score, rank) for title, score, rank, _ in rankings]

    return ui.layout(ui.ranking_view(list_id, display_items, meta, is_streaming=True))


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

            # Yield SSE event with full container replacement
            yield f"event: datastar-fragment\n"
            yield f"data: {new_html}\n\n"

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

    yield f"event: datastar-fragment\n"
    yield f"data: {final_html}\n\n"


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
