from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager
import logging
import os
import httpx
from postmarker.core import PostmarkClient
from src import storage
from src.parser import EmailDSLParser
from src.reducer import Reducer, ParseError
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
    for email_body in storage.stream_history():
        count += 1
        # TODO: Feed this body into the Grammar Parser
        # parser.process(email_body, GLOBAL_STATE)
        pass
    
    GLOBAL_STATE["email_count"] = count
    logger.info(f"--- STARTUP COMPLETE: Replayed {count} events ---")
    
    yield
    
    logger.info("--- SHUTDOWN ---")


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="src/templates")

# Initialize Postmark client
postmark_token = os.getenv("POSTMARK_SERVER_TOKEN")
postmark = PostmarkClient(server_token=postmark_token) if postmark_token else None
if not postmark:
    logger.warning("POSTMARK_SERVER_TOKEN not set - email sending disabled")

# Initialize parser and reducer
parser = EmailDSLParser()
reducer = Reducer()

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
+ = item title (creates or references an item)

Basic Structure:
#hashtag-name
+item-title { optional body text }

Votes (pairwise comparisons):
+item1 10:1 +item2    (explicit ratio - item1 is 10x better)
+item1 > +item2       (clearly better, 2:1 ratio)
+item1 < +item2       (clearly worse, 1:2 ratio)
+item1 = +item2       (equal preference, 1:1 ratio)

Attributes (set voting context):
:difficulty
+item1 > +item2       (this vote is about difficulty)

Bodies (with nested braces support):
+item { single line body }
+item {
  multi-line body
  with multiple lines
}
+item {{ body with { nested } braces }}

Rules:
- Items must be under a hashtag (use #hashtag first)
- Votes require both items to exist first
- Lines starting with #:+@ are parsed, others ignored
- No zero ratios allowed (breaks ranking algorithm)

Example:
#ideas
+write-parser { Build the EmailDSL parser }
+fix-auth { Fix authentication bug }
:difficulty
+write-parser > +fix-auth
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

def build_reply_body(original_text: str) -> str:
    """Construct the text body for an auto-reply with quoted text"""
    quoted = "\n".join(f"> {line}" for line in original_text.splitlines())
    return f"Thanks for your email!\n\n{quoted}"

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    emails = storage.list_emails()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "count": GLOBAL_STATE["email_count"],
        "emails": emails
    })


@app.get("/emails/{filename}", response_class=PlainTextResponse)
async def get_email(filename: str):
    """Serve a specific email file as plain text"""
    result = storage.get_email(filename)
    if result is None:
        return PlainTextResponse("Email not found", status_code=404)
    body, from_email, timestamp = result
    return PlainTextResponse(body)

@app.post("/webhook/postmark")
async def postmark_webhook(email: PostmarkInboundEmail):
    """
    Webhook endpoint for Postmark inbound emails.
    Receives emails sent to anything@mail.sorter.social
    """
    logger.info(f"Received email from {email.From} to {email.To}")

    # 1. Persist to Disk (Append-Only Log)
    # We use the TextBody as the source of truth for the parser
    storage.save_email(email.Subject, email.TextBody, from_email=email.From)
    # Update local state immediately so we don't need to restart to see changes
    GLOBAL_STATE["email_count"] += 1

    # 2. Parse and validate the email
    parse_error_message = None
    try:
        # Parse with line filtering (ignores email signatures, etc.)
        doc = parser.parse_lines(email.TextBody)
        # Run semantic validation (reducer checks hashtag context, forward refs, zero ratios)
        reducer.process_document(doc, user_email=email.From)
        logger.info(f"Successfully parsed email from {email.From}")
    except (LarkError, ParseError) as e:
        # Parsing or semantic validation failed
        parse_error_message = str(e)
        logger.warning(f"Parse error from {email.From}: {parse_error_message}")

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
        # Parse failed - get LLM explanation
        logger.info(f"Getting LLM explanation for parse error from {email.From}")
        reply_body = await explain_parse_error(email.TextBody, parse_error_message, GRAMMAR_DOC)
        reply_body = f"⚠️ Your email couldn't be parsed:\n\n{reply_body}\n\n---\nOriginal email:\n{build_reply_body(email.TextBody)}"
    else:
        # Parse succeeded - send success confirmation
        reply_body = f"✅ Your email was successfully processed!\n\n{build_reply_body(email.TextBody)}"

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

