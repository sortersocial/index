from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager
import asyncio
import logging
import os
import time
from datetime import datetime
import humanize
import httpx
from postmarker.core import PostmarkClient
from src import storage
from src.parser import EmailDSLParser, Hashtag
from src.reducer import Reducer, ParseError
from src.rank import compute_rankings_from_state
from lark.exceptions import LarkError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Global In-Memory State ---
# This will be populated from the file system at startup
GLOBAL_STATE = {
    "email_count": 0,
    # TODO: Add "Graph", "Entities", "Slugs" here
}


def format_markdown(text: Optional[str]) -> str:
    """Convert markdown to HTML with syntax highlighting."""
    if not text:
        return ""
    import markdown
    from markupsafe import Markup
    html = markdown.markdown(
        text,
        extensions=['fenced_code', 'codehilite', 'nl2br'],
        extension_configs={
            'codehilite': {
                'css_class': 'highlight',
                'guess_lang': False
            }
        }
    )
    return Markup(html)


def format_relative_time(timestamp_str: Optional[str]) -> str:
    """
    Format a unix timestamp string as relative time using humanize.

    Args:
        timestamp_str: Unix timestamp in milliseconds as string, or None

    Returns:
        Formatted relative time string (e.g., "10 seconds ago")
    """
    if not timestamp_str:
        return "never"

    try:
        timestamp_ms = float(timestamp_str)
        # Convert milliseconds to seconds for datetime.fromtimestamp
        timestamp_seconds = timestamp_ms / 1000.0
        dt = datetime.fromtimestamp(timestamp_seconds)
        return humanize.naturaltime(dt)
    except (ValueError, TypeError):
        return "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager to handle startup and shutdown events.
    Replays the append-only log to rebuild in-memory state.
    """
    logger.info("--- STARTUP: Replaying History ---")
    
    # Initialize storage (ensure dir exists)
    storage.init_storage()
    
    # Replay history
    count = 0
    errors = 0
    for body, from_email, timestamp, filename in storage.stream_history():
        count += 1
        try:
            # Parse and process each historical email
            doc = parser.parse_lines(body)
            if any(s is not None for s in doc.statements):
                # Re-use the exact same logic as the webhook
                reducer.process_document(doc, user_email=from_email, timestamp=timestamp, source_filename=filename)
        except Exception as e:
            errors += 1
            logger.error(f"Failed to replay email {count}: {e}")

    GLOBAL_STATE["email_count"] = count
    logger.info(f"--- STARTUP COMPLETE: Replayed {count} events ({errors} errors) ---")
    logger.info(f"State: {len(reducer.state.items)} items, {len(reducer.state.votes)} votes")
    
    yield
    
    logger.info("--- SHUTDOWN ---")


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="src/templates")

# Mount static files
app.mount("/static", StaticFiles(directory="src/static"), name="static")

# Add custom filters to Jinja2
templates.env.filters["relative_time"] = format_relative_time
templates.env.filters["markdown"] = format_markdown

# Initialize Postmark client
postmark_token = os.getenv("POSTMARK_SERVER_TOKEN")
postmark = PostmarkClient(server_token=postmark_token) if postmark_token else None
if not postmark:
    logger.warning("POSTMARK_SERVER_TOKEN not set - email sending disabled")

# Initialize parser and reducer
parser = EmailDSLParser()
reducer = Reducer()

# Concurrency lock to protect reducer state
reducer_lock = asyncio.Lock()

# OpenRouter configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY not set - LLM error explanations disabled")

# EmailDSL Grammar Documentation
GRAMMAR_DOC = """
EmailDSL Grammar:

# = hashtag (creates category context)
: = attribute (sets comparison dimension)
- = item title (creates or references an item)

Basic Structure:
#hashtag-name
-item-title { optional body text }

Votes (pairwise comparisons):
-item1 10:1 -item2    (explicit ratio - item1 is 10x better)
-item1 > -item2       (clearly better, 2:1 ratio)
-item1 < -item2       (clearly worse, 1:2 ratio)
-item1 = -item2       (equal preference, 1:1 ratio)

Attributes (set voting context):
:difficulty
-item1 > -item2       (this vote is about difficulty)

Bodies (with nested braces support):
-item { single line body }
-item {
  multi-line body
  with multiple lines
}
-item {{ body with { nested } braces }}

Rules:
- Items must be under a hashtag (use #hashtag first)
- Votes require both items to exist first
- Lines starting with #:-@ are parsed, others ignored
- No zero ratios allowed (breaks ranking algorithm)

Example:
#ideas
-write-parser { Build the EmailDSL parser }
-fix-auth { Fix authentication bug }
:difficulty
-write-parser > -fix-auth
"""


async def explain_parse_error(user_email: str, error_message: str, grammar: str) -> str:
    """
    Use OpenRouter (Haiku 4.5) to explain a parse error in friendly terms.

    Args:
        user_email: The email body that failed to parse
        error_message: The error message from the parser
        grammar: The EmailDSL grammar documentation

    Returns:
        A friendly explanation of what went wrong
    """
    prompt = f"""You are helping a user debug their EmailDSL submission. They sent an email that failed to parse.

Here is the EmailDSL grammar:
{grammar}

Here is the email they sent:
```
{user_email}
```

Here is the error message:
```
{error_message}
```

Please explain in friendly, clear terms:
1. What they did wrong
2. How to fix it
3. Show a corrected example

Be concise and helpful. Assume they're smart but new to the syntax."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "anthropic/claude-3.5-haiku",
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                },
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"OpenRouter API error: {e}")
        # Fallback to just the raw error
        return f"Parse error: {error_message}\n\nPlease check the EmailDSL syntax and try again."


def format_rankings_with_deltas(
    rankings_before: List[tuple],
    rankings_after: List[tuple],
    max_items: int = 100
) -> str:
    """
    Format rankings showing before/after with deltas.

    Args:
        rankings_before: List of (title, score, rank) before processing
        rankings_after: List of (title, score, rank) after processing
        max_items: Maximum number of items to show

    Returns:
        Formatted string showing rankings with deltas
    """
    if not rankings_after:
        return "No items to rank yet."

    # Build a map of title -> old rank
    old_ranks = {title: rank for title, _, rank in rankings_before} if rankings_before else {}

    # Format output
    lines = ["## Rankings (Top {})".format(min(len(rankings_after), max_items)), ""]

    for title, score, new_rank in rankings_after[:max_items]:
        old_rank = old_ranks.get(title)

        if old_rank is None:
            # New item
            delta_str = " (new)"
        elif old_rank == new_rank:
            # No change
            delta_str = ""
        else:
            # Rank changed (note: lower rank number = better, so +1 means moved up)
            delta = old_rank - new_rank
            if delta > 0:
                delta_str = f" (+{delta})"
            else:
                delta_str = f" ({delta})"

        lines.append(f"{new_rank}. {title}{delta_str}")

    if len(rankings_after) > max_items:
        lines.append(f"\n... and {len(rankings_after) - max_items} more items")

    return "\n".join(lines)


async def respond_to_natural_language(user_message: str, grammar: str) -> str:
    """
    Respond to natural language queries about the system.

    Args:
        user_message: The user's message
        grammar: The EmailDSL grammar documentation

    Returns:
        A helpful response explaining what sorter is and how to use it
    """
    prompt = f"""You are Sorter, an email-based system for collaborative ranking and decision-making.

A user sent you an email that doesn't contain any EmailDSL commands. Here's what they said:

```
{user_message}
```

Respond naturally to their message. If they're asking what you are, explain:
- You're a competitive folksonomy system that ranks items via pairwise comparisons
- Users submit items and votes by email using a simple DSL
- The system uses rank centrality (stationary distribution of a Markov chain) to compute rankings

Then briefly explain the EmailDSL syntax:
{grammar}

Be friendly, concise, and encouraging. Invite them to try it out."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "anthropic/claude-3.5-haiku",
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                },
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"OpenRouter API error: {e}")
        # Fallback response
        return f"""Hello! I'm Sorter, an email-based ranking system.

I help you rank items through pairwise comparisons using a simple email syntax. To use me, send emails with:

#category - create a category
+item-name {{ description }} - add items
+item1 > +item2 - vote (item1 is better)

Try sending an email with those commands to get started!"""


# Postmark Inbound Email Schema
class PostmarkAttachment(BaseModel):
    Name: str
    Content: str
    ContentType: str
    ContentLength: int

class PostmarkInboundEmail(BaseModel):
    FromName: Optional[str] = None
    From: str
    FromFull: dict
    To: str
    ToFull: List[dict]
    Cc: Optional[str] = None
    CcFull: Optional[List[dict]] = None
    Bcc: Optional[str] = None
    BccFull: Optional[List[dict]] = None
    OriginalRecipient: str
    Subject: str
    MessageID: str
    ReplyTo: Optional[str] = None
    MailboxHash: Optional[str] = None
    Date: str
    TextBody: str
    HtmlBody: str
    StrippedTextReply: Optional[str] = None
    Tag: Optional[str] = None
    Headers: List[dict]
    Attachments: List[PostmarkAttachment] = []

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    emails = storage.list_emails()

    # Acquire lock for consistent read of reducer state
    async with reducer_lock:
        # Collect hashtag statistics from reducer state
        hashtag_stats = {}
        for item_title, item_record in reducer.state.items.items():
            for hashtag in item_record.hashtags:
                if hashtag not in hashtag_stats:
                    hashtag_stats[hashtag] = {"items": 0, "votes": 0, "last_updated": None}
                hashtag_stats[hashtag]["items"] += 1
                # Track most recent timestamp for this hashtag
                if item_record.timestamp:
                    current_ts = hashtag_stats[hashtag]["last_updated"]
                    if current_ts is None or item_record.timestamp > current_ts:
                        hashtag_stats[hashtag]["last_updated"] = item_record.timestamp

        # Count votes per hashtag (count votes where both items share the hashtag)
        for vote in reducer.state.votes:
            item1_hashtags = reducer.state.items[vote.item1].hashtags
            item2_hashtags = reducer.state.items[vote.item2].hashtags
            shared_hashtags = item1_hashtags & item2_hashtags
            for hashtag in shared_hashtags:
                if hashtag in hashtag_stats:
                    hashtag_stats[hashtag]["votes"] += 1
                    # Update timestamp from vote if more recent
                    if vote.timestamp:
                        current_ts = hashtag_stats[hashtag]["last_updated"]
                        if current_ts is None or vote.timestamp > current_ts:
                            hashtag_stats[hashtag]["last_updated"] = vote.timestamp

        # Sort hashtags by most recently updated
        sorted_hashtags = sorted(
            hashtag_stats.items(),
            key=lambda x: x[1]["last_updated"] or "0",
            reverse=True
        )

    return templates.TemplateResponse("index.html", {
        "request": request,
        "count": GLOBAL_STATE["email_count"],
        "emails": emails,
        "hashtags": sorted_hashtags
    })


@app.get("/emails/{filename}/raw", response_class=PlainTextResponse)
async def get_email_raw(filename: str):
    """Serve email as raw plaintext"""
    result = storage.get_email(filename)
    if result is None:
        return PlainTextResponse("Email not found", status_code=404)
    body, from_email, timestamp = result
    return PlainTextResponse(body)


@app.get("/emails/{filename}", response_class=HTMLResponse)
async def get_email(request: Request, filename: str):
    """Serve email with parsed content and links"""
    result = storage.get_email(filename)
    if result is None:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "message": "Email not found"
        }, status_code=404)

    body, from_email, timestamp = result

    # Parse the email to extract structure
    try:
        doc = parser.parse_lines(body)
        parsed = True
    except:
        doc = None
        parsed = False

    return templates.TemplateResponse("email.html", {
        "request": request,
        "filename": filename,
        "body": body,
        "from_email": from_email,
        "timestamp": timestamp,
        "doc": doc,
        "parsed": parsed
    })


@app.get("/user/{user_email}", response_class=HTMLResponse)
async def view_user(request: Request, user_email: str):
    """View all items and votes by a specific user"""
    async with reducer_lock:
        # Get items created by this user
        user_items = [
            (title, record)
            for title, record in reducer.state.items.items()
            if record.created_by == user_email
        ]

        # Get votes by this user
        user_votes = [
            vote for vote in reducer.state.votes
            if vote.user_email == user_email
        ]

    return templates.TemplateResponse("user.html", {
        "request": request,
        "user_email": user_email,
        "items": user_items,
        "votes": user_votes
    })


@app.get("/compare/{item1}/vs/{item2}", response_class=HTMLResponse)
async def compare_items(request: Request, item1: str, item2: str, attribute: str = None):
    """View comparison between two specific items with all votes and arguments"""
    from src.reducer import State
    from starlette.responses import RedirectResponse
    from collections import Counter

    # Canonicalize URL: always sort items alphabetically
    if item1 > item2:
        canonical_url = f"/compare/{item2}/vs/{item1}"
        if attribute:
            canonical_url += f"?attribute={attribute}"
        return RedirectResponse(url=canonical_url, status_code=301)

    async with reducer_lock:
        # Get the item records
        item1_record = reducer.state.items.get(item1)
        item2_record = reducer.state.items.get(item2)

        if not item1_record or not item2_record:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "message": f"One or both items not found: {item1}, {item2}"
            }, status_code=404)

        # Find all votes between these two items (in either direction)
        all_comparison_votes = [
            vote for vote in reducer.state.votes
            if ((vote.item1 == item1 and vote.item2 == item2) or
                (vote.item1 == item2 and vote.item2 == item1))
            and vote.attribute is not None
        ]

        # Discover available attributes and their vote counts
        attribute_counts = Counter(vote.attribute for vote in all_comparison_votes)
        available_attributes = sorted(attribute_counts.items(), key=lambda x: x[1], reverse=True)

        # If no attribute specified, use the one with most votes
        if attribute is None and available_attributes:
            attribute = available_attributes[0][0]

        # Filter votes by selected attribute
        comparison_votes = [
            vote for vote in all_comparison_votes
            if vote.attribute == attribute
        ] if attribute else []

        # Calculate aggregate preference
        item1_preference = 0.0
        item2_preference = 0.0

        for vote in comparison_votes:
            if vote.item1 == item1:
                # Vote is item1 vs item2
                item1_preference += vote.ratio_left
                item2_preference += vote.ratio_right
            else:
                # Vote is item2 vs item1
                item2_preference += vote.ratio_left
                item1_preference += vote.ratio_right

        total_votes = item1_preference + item2_preference
        item1_percentage = int((item1_preference / total_votes * 100)) if total_votes > 0 else 50

        # Find common hashtags
        common_hashtags = set(item1_record.hashtags) & set(item2_record.hashtags)

    return templates.TemplateResponse("compare.html", {
        "request": request,
        "item1": item1,
        "item2": item2,
        "item1_record": item1_record,
        "item2_record": item2_record,
        "votes": comparison_votes,
        "available_attributes": available_attributes,
        "current_attribute": attribute,
        "item1_preference": item1_preference,
        "item2_preference": item2_preference,
        "item1_percentage": item1_percentage,
        "common_hashtags": common_hashtags,
    })


@app.get("/hashtag/{hashtag_name}", response_class=HTMLResponse)
async def view_hashtag(request: Request, hashtag_name: str, attribute: str = None):
    """View items under a specific hashtag, ranked by attribute"""
    from src.reducer import State
    from collections import Counter

    # Acquire lock for consistent read of reducer state
    async with reducer_lock:
        # Get all items under this hashtag
        items_in_hashtag = {
            title: record
            for title, record in reducer.state.items.items()
            if hashtag_name in record.hashtags
        }

        if not items_in_hashtag:
            return templates.TemplateResponse("hashtag.html", {
                "request": request,
                "hashtag": hashtag_name,
                "items": [],
                "available_attributes": [],
                "current_attribute": None,
                "components": []
            })

        # Filter votes to only votes between items in this hashtag
        hashtag_item_titles = set(items_in_hashtag.keys())
        hashtag_votes = [
            vote for vote in reducer.state.votes
            if vote.item1 in hashtag_item_titles and vote.item2 in hashtag_item_titles
            and vote.attribute is not None
        ]

        # Discover available attributes and their vote counts
        attribute_counts = Counter(vote.attribute for vote in hashtag_votes)
        available_attributes = sorted(attribute_counts.items(), key=lambda x: x[1], reverse=True)

        # If no attribute specified, use the one with most votes
        if attribute is None and available_attributes:
            attribute = available_attributes[0][0]

        # If still no attribute (no votes at all), show empty state
        if attribute is None:
            return templates.TemplateResponse("hashtag.html", {
                "request": request,
                "hashtag": hashtag_name,
                "items": list(items_in_hashtag.items()),
                "available_attributes": [],
                "current_attribute": None,
                "components": []
            })

        # Compute rankings for this hashtag and attribute
        hashtag_rankings = compute_rankings_from_state(
            reducer.state,
            hashtag=hashtag_name,
            attribute=attribute
        )

        # Group by component
        from collections import defaultdict
        components_dict = defaultdict(list)
        for title, score, rank, comp_id in hashtag_rankings:
            components_dict[comp_id].append((title, score, rank, items_in_hashtag[title]))

        # Convert to list of components for template
        components = [
            {
                "id": comp_id,
                "items": items
            }
            for comp_id, items in sorted(components_dict.items())
        ]

    # Filter votes by current attribute for display
    attribute_votes = [v for v in hashtag_votes if v.attribute == attribute] if attribute else []

    return templates.TemplateResponse("hashtag.html", {
        "request": request,
        "hashtag": hashtag_name,
        "available_attributes": available_attributes,
        "current_attribute": attribute,
        "components": components,
        "votes": attribute_votes,
        "vote_count": len(attribute_votes)
    })


@app.post("/webhook/postmark")
async def postmark_webhook(email: PostmarkInboundEmail):
    """
    Webhook endpoint for Postmark inbound emails.
    Receives emails sent to anything@mail.sorter.social
    """
    logger.info(f"Received email from {email.From} to {email.To}")

    # 1. Parse and validate the email first
    parse_error_message = None
    doc = None
    has_dsl_commands = False
    rankings_before = None
    rankings_after = None

    try:
        # Parse with line filtering (ignores email signatures, etc.)
        doc = parser.parse_lines(email.TextBody)
        # Check if document has any actual statements (not just None)
        has_dsl_commands = any(s is not None for s in doc.statements)

        if has_dsl_commands:
            from src.reducer import State

            # Extract hashtags mentioned in this email
            mentioned_hashtags = {
                stmt.name for stmt in doc.statements
                if isinstance(stmt, Hashtag)
            }

            # Generate timestamp once to use for both reducer and storage
            current_timestamp = int(time.time() * 1000)  # milliseconds

            # Acquire lock to prevent concurrent modifications to reducer state
            async with reducer_lock:
                # TODO: Before/after ranking comparison disabled pending attribute-aware implementation
                # The new ranking model requires (hashtag, attribute) pairs, but emails may
                # mention multiple hashtags and attributes. Need to redesign this feature.
                rankings_before = []
                rankings_after = []

                # 2. Persist to Disk BEFORE processing (so we have filename)
                # Use the same timestamp for consistency
                filename, timestamp_str = storage.save_email(
                    email.Subject, email.TextBody,
                    from_email=email.From,
                    timestamp=current_timestamp
                )

                # Run semantic validation (reducer checks hashtag context, forward refs, zero ratios, attributes)
                reducer.process_document(doc, user_email=email.From, timestamp=str(current_timestamp), source_filename=filename)

            GLOBAL_STATE["email_count"] += 1
            logger.info(f"Successfully parsed and stored email from {email.From}")
        else:
            logger.info(f"Email from {email.From} contains no DSL commands")
    except (LarkError, ParseError) as e:
        # Parsing or semantic validation failed
        parse_error_message = str(e)
        logger.warning(f"Parse error from {email.From}: {parse_error_message}")

        # Save the problematic email for debugging
        try:
            debug_timestamp = int(__import__('time').time() * 1000)
            debug_filename = f"debug_{debug_timestamp}_{email.From.replace('@', '_at_')}.txt"
            debug_path = storage.DATA_DIR / debug_filename
            debug_path.write_text(f"Subject: {email.Subject}\n\nBody:\n{email.TextBody}", encoding="utf-8")
            logger.info(f"Saved problematic email to {debug_filename}")
        except Exception as debug_err:
            logger.error(f"Failed to save debug email: {debug_err}")

    # 3. Send Auto-Reply
    if not postmark:
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Email received (no reply sent)"}
        )
    
    # Extract threading headers
    incoming_message_id = None
    incoming_references = None
    
    for header in email.Headers:
        header_name = header.get("Name", "")
        if header_name.lower() == "message-id":
            incoming_message_id = header.get("Value")
        elif header_name.lower() == "references":
            incoming_references = header.get("Value")

    reply_references = f"{incoming_references} {incoming_message_id}" if incoming_references else incoming_message_id
    subject = email.Subject if email.Subject.startswith("Re:") else f"Re: {email.Subject}"
    reply_from = email.To  # Reply from the specific address (e.g. random-slug@sorter.social)

    # Determine reply body based on parse result
    if parse_error_message:
        # Case 1: Parse failed - get LLM explanation
        logger.info(f"Getting LLM explanation for parse error from {email.From}")
        explanation = await explain_parse_error(email.TextBody, parse_error_message, GRAMMAR_DOC)
        quoted = "\n".join(f"> {line}" for line in email.TextBody.splitlines())
        reply_body = f"⚠️ Your email couldn't be parsed:\n\n{explanation}\n\n---\nOriginal email:\n\n{quoted}"
    elif not has_dsl_commands:
        # Case 2: No DSL commands - respond naturally
        logger.info(f"Responding to natural language query from {email.From}")
        reply_body = await respond_to_natural_language(email.TextBody, GRAMMAR_DOC)
    else:
        # Case 3: Valid DSL - send success confirmation with rankings
        rankings_text = format_rankings_with_deltas(rankings_before, rankings_after)
        reply_body = f"✅ Your email was successfully processed!\n\n{rankings_text}"

    postmark.emails.send(
        From=reply_from,
        To=email.From,
        Subject=subject,
        TextBody=reply_body,
        Headers={
            "In-Reply-To": incoming_message_id,
            "References": reply_references
        },
        TrackOpens=False,
        TrackLinks="None"
    )
    logger.info(f"Sent reply to {email.From}")

    return JSONResponse(
        status_code=200,
        content={"status": "success", "message": "Email processed"}
    )

@app.get("/health")
async def health_check():
    """Health check endpoint for fly.io"""
    return {"status": "healthy"}

