from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager
import logging
import os
from postmarker.core import PostmarkClient
from src import storage

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
    return templates.TemplateResponse("index.html", {
        "request": request,
        "count": GLOBAL_STATE["email_count"]
    })

@app.post("/webhook/postmark")
async def postmark_webhook(email: PostmarkInboundEmail):
    """
    Webhook endpoint for Postmark inbound emails.
    Receives emails sent to anything@mail.sorter.social
    """
    logger.info(f"Received email from {email.From} to {email.To}")

    # 1. Persist to Disk (Append-Only Log)
    # We use the TextBody as the source of truth for the parser
    storage.save_email(email.Subject, email.TextBody)
    # Update local state immediately so we don't need to restart to see changes
    GLOBAL_STATE["email_count"] += 1

    # 2. Send Auto-Reply
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
    
    postmark.emails.send(
        From=reply_from,
        To=email.From,
        Subject=subject,
        TextBody=build_reply_body(email.TextBody),
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

